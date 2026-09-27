import os
import sys
import json
import time
import asyncio
import tempfile
import subprocess
import webbrowser
import urllib.parse
import threading
import traceback
import difflib
import ctypes
from datetime import datetime

import speech_recognition as sr
import edge_tts
import pygame
from openai import OpenAI
import pystray
from PIL import Image, ImageDraw

def app_dir():
    return os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))

BASE_DIR = app_dir()
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", BASE_DIR), "Artemis")
os.makedirs(DATA_DIR, exist_ok=True)
LOG_FILE = os.path.join(DATA_DIR, "artemis.log")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass

try:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except Exception:
    CONFIG = {}

NAME = CONFIG.get("assistant_name", "Artemis").lower()
VOICE = CONFIG.get("voice", "pt-BR-FranciscaNeural")
MODEL = CONFIG.get("ai_model", "gpt-5.6-luna")
WAKE_REQUIRED = CONFIG.get("wake_word_required", True)
CONFIRM_POWER = CONFIG.get("confirm_power_actions", True)

recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True
recognizer.pause_threshold = 0.65

shutdown_event = threading.Event()
tts_lock = threading.Lock()

try:
    pygame.mixer.init()
except Exception as e:
    log("pygame init: " + repr(e))

def speak(text):
    log("Artemis: " + text)
    def worker():
        with tts_lock:
            path = os.path.join(tempfile.gettempdir(), "artemis_voice.mp3")
            try:
                async def make_audio():
                    communicate = edge_tts.Communicate(text, VOICE)
                    await communicate.save(path)
                asyncio.run(make_audio())
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and not shutdown_event.is_set():
                    time.sleep(0.05)
            except Exception as e:
                log("TTS error: " + repr(e))
    threading.Thread(target=worker, daemon=True).start()

def listen():
    try:
        with sr.Microphone() as source:
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=12)
        text = recognizer.recognize_google(audio, language="pt-BR").lower().strip()
        log("Você: " + text)
        return text
    except sr.WaitTimeoutError:
        return ""
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        log("STT error: " + repr(e))
        time.sleep(1)
        return ""

def normalize(s):
    return " ".join(s.lower().replace(",", " ").replace(".", " ").split())

def get_start_apps():
    """Returns [(name, app_id)] from the Windows Start menu."""
    try:
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
            "Get-StartApps | ForEach-Object { $_.Name + \"|||\" + $_.AppID }"
        ]
        p = subprocess.run(cmd, capture_output=True, text=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                           timeout=12)
        result=[]
        for line in p.stdout.splitlines():
            if "|||" in line:
                name, appid = line.split("|||", 1)
                result.append((name.strip(), appid.strip()))
        return result
    except Exception as e:
        log("StartApps error: " + repr(e))
        return []

def open_any_app(target):
    target = normalize(target)
    apps = get_start_apps()

    # Exact/contained match first.
    for name, appid in apps:
        n = normalize(name)
        if target == n or target in n or n in target:
            try:
                subprocess.Popen(
                    ["explorer.exe", f"shell:AppsFolder\\{appid}"],
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return True, name
            except Exception as e:
                log("App launch error: " + repr(e))

    # Fuzzy matching.
    names = [normalize(n) for n, _ in apps]
    matches = difflib.get_close_matches(target, names, n=1, cutoff=0.55)
    if matches:
        best = matches[0]
        for name, appid in apps:
            if normalize(name) == best:
                try:
                    subprocess.Popen(
                        ["explorer.exe", f"shell:AppsFolder\\{appid}"],
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    return True, name
                except Exception:
                    pass

    # Classic executables available on PATH.
    try:
        if shutil.which(target):
            subprocess.Popen([target], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return True, target
    except Exception:
        pass

    return False, None

def media_key(vk):
    try:
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception as e:
        log("media key error: " + repr(e))
        return False

VK_MEDIA_PLAY_PAUSE=0xB3
VK_VOLUME_MUTE=0xAD
VK_VOLUME_DOWN=0xAE
VK_VOLUME_UP=0xAF
VK_LWIN=0x5B
VK_L=0x4C

def power_action(action):
    if action == "shutdown":
        subprocess.Popen(["shutdown", "/s", "/t", "0"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif action == "restart":
        subprocess.Popen(["shutdown", "/r", "/t", "0"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    elif action == "lock":
        ctypes.windll.user32.LockWorkStation()
    elif action == "logoff":
        subprocess.Popen(["shutdown", "/l"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

def web_search(q):
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(q))

SYSTEM = """Você é o cérebro de Artemis, uma assistente virtual feminina para Windows.
Responda ao comando do usuário escolhendo UMA ação do catálogo abaixo.
O usuário fala naturalmente em português brasileiro. Entenda variações, erros de fala e frases informais.
NUNCA invente uma ação fora do catálogo.
Retorne SOMENTE JSON válido no formato:
{"action":"...","target":"...","query":"...","reply":"...","needs_confirmation":false}

Ações:
open_app: abre qualquer aplicativo instalado encontrado no menu Iniciar. target = nome do app.
media_play_pause: alterna play/pause de mídia.
volume_up: aumenta volume.
volume_down: diminui volume.
volume_mute: silencia/reativa volume.
search_web: pesquisa na web. query = pesquisa.
open_url: abre uma URL. target = URL.
shutdown: desliga o Windows.
restart: reinicia o Windows.
lock: bloqueia o Windows.
logoff: encerra a sessão do Windows.
time: informa hora.
close_app: fecha um aplicativo pelo nome, SOMENTE quando solicitado explicitamente. target = app.
chat: conversa/responde sem executar ação.

Para ações destrutivas (shutdown, restart, logoff), needs_confirmation deve ser true.
Para abrir apps, media, volume, pesquisa, URL e bloquear, false.
reply deve ser curta e natural, em português-BR.
"""

def ai_command(text):
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        client = OpenAI(api_key=key)
        response = client.responses.create(
            model=MODEL,
            instructions=SYSTEM,
            input=text
        )
        raw = response.output_text.strip()
        log("AI: " + raw)
        return json.loads(raw)
    except Exception as e:
        log("AI error: " + repr(e))
        return None

def local_command(text):
    t = normalize(text)

    # Power actions first.
    if any(x in t for x in ["desligue o pc", "desligar o pc", "desligue meu computador", "desligar meu computador"]):
        return {"action":"shutdown","reply":"Vou desligar o computador. Confirma?","needs_confirmation":True}
    if any(x in t for x in ["reinicie o pc", "reiniciar o pc", "reinicie meu computador", "reiniciar meu computador"]):
        return {"action":"restart","reply":"Vou reiniciar o computador. Confirma?","needs_confirmation":True}
    if "bloqueie o pc" in t or "bloquear o pc" in t or "bloqueie meu computador" in t:
        return {"action":"lock","reply":"Bloqueando o computador.","needs_confirmation":False}
    if "sair da conta" in t or "encerrar sessão" in t or "encerrar sessao" in t:
        return {"action":"logoff","reply":"Vou encerrar sua sessão. Confirma?","needs_confirmation":True}

    if any(x in t for x in ["despausar", "dar play", "pausar a música", "pausar musica", "continuar música", "continuar musica", "continue a música", "continue a musica"]):
        return {"action":"media_play_pause","reply":"Certo.","needs_confirmation":False}

    if "aumenta o volume" in t or "aumente o volume" in t:
        return {"action":"volume_up","reply":"Aumentando o volume.","needs_confirmation":False}
    if "abaixa o volume" in t or "diminui o volume" in t or "diminua o volume" in t:
        return {"action":"volume_down","reply":"Diminuindo o volume.","needs_confirmation":False}
    if "muta o volume" in t or "silencia o volume" in t:
        return {"action":"volume_mute","reply":"Silenciando o volume.","needs_confirmation":False}

    if t.startswith("pesquise ") or t.startswith("pesquisar ") or t.startswith("procure "):
        return {"action":"search_web","query":text.split(" ",1)[1],"reply":"Vou pesquisar.","needs_confirmation":False}

    # Common natural open phrases.
    for prefix in ["abra ", "abrir ", "abre ", "inicie ", "iniciar ", "inicia ", "execute ", "executar "]:
        if t.startswith(prefix):
            return {"action":"open_app","target":text[len(prefix):].strip(),"reply":"Claro.","needs_confirmation":False}

    if "que horas" in t:
        return {"action":"time","reply":"","needs_confirmation":False}

    return None

def execute(cmd):
    if not cmd:
        speak("Não consegui entender esse comando.")
        return

    action=cmd.get("action")
    target=cmd.get("target","")
    reply=cmd.get("reply","")
    needs=bool(cmd.get("needs_confirmation",False))

    if action in ("shutdown","restart","logoff") and needs and CONFIRM_POWER:
        speak(reply)
        confirmation = listen()
        c=normalize(confirmation)
        if any(x in c for x in ["sim", "pode", "confirmo", "confirmado", "faça", "faca"]):
            speak("Certo.")
            power_action(action)
        else:
            speak("Tudo bem, cancelei.")
        return

    if action=="open_app":
        ok, name=open_any_app(target)
        speak(f"Abrindo {name}." if ok else f"Não encontrei {target} no menu Iniciar.")
    elif action=="media_play_pause":
        media_key(VK_MEDIA_PLAY_PAUSE); speak(reply or "Certo.")
    elif action=="volume_up":
        media_key(VK_VOLUME_UP); speak(reply or "Certo.")
    elif action=="volume_down":
        media_key(VK_VOLUME_DOWN); speak(reply or "Certo.")
    elif action=="volume_mute":
        media_key(VK_VOLUME_MUTE); speak(reply or "Certo.")
    elif action=="search_web":
        web_search(cmd.get("query",target)); speak(reply or "Pesquisando.")
    elif action=="open_url":
        webbrowser.open(target); speak(reply or "Abrindo.")
    elif action=="shutdown":
        power_action("shutdown")
    elif action=="restart":
        power_action("restart")
    elif action=="lock":
        power_action("lock"); speak(reply or "Computador bloqueado.")
    elif action=="logoff":
        power_action("logoff")
    elif action=="time":
        speak("Agora são " + datetime.now().strftime("%H:%M"))
    elif action=="close_app":
        # Conservative: close via taskkill only after explicit command.
        try:
            subprocess.Popen(["taskkill","/IM",target,"/F"], creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            speak(f"Fechando {target}.")
        except Exception:
            speak(f"Não consegui fechar {target}.")
    else:
        speak(reply or "Certo.")

def handle(text):
    clean=text
    if WAKE_REQUIRED:
        pos=clean.find(NAME)
        if pos < 0:
            return
        clean=clean[pos+len(NAME):].strip(" ,.!?")

    if not clean:
        speak("Sim? Estou ouvindo.")
        return

    if clean in ("sair", "encerrar", "fechar a artemis"):
        speak("Até logo.")
        shutdown_event.set()
        return

    cmd=ai_command(clean)
    if cmd is None:
        cmd=local_command(clean)
    execute(cmd)

def voice_loop():
    speak("Artemis está online.")
    while not shutdown_event.is_set():
        text=listen()
        if text:
            try:
                handle(text)
            except Exception as e:
                log("Command error: " + repr(e))

def tray_image():
    img=Image.new("RGBA",(64,64),(0,0,0,0))
    d=ImageDraw.Draw(img)
    d.ellipse((4,4,60,60),fill=(40,180,120,255))
    d.ellipse((15,18,25,28),fill="white")
    d.ellipse((39,18,49,28),fill="white")
    d.arc((18,20,46,48),0,180,fill="white",width=3)
    return img

def exit_app(icon,item):
    shutdown_event.set()
    icon.stop()

def main():
    log("=== ARTEMIS v2 INICIANDO ===")
    threading.Thread(target=voice_loop,daemon=True).start()
    icon=pystray.Icon("Artemis",tray_image(),"Artemis",pystray.Menu(
        pystray.MenuItem("Sair",exit_app)
    ))
    icon.run()

if __name__=="__main__":
    try:
        main()
    except Exception:
        log(traceback.format_exc())
