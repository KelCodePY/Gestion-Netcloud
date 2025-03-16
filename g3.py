import gspread
from telethon import TelegramClient, events
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, jsonify
import asyncio
import re
import unidecode
import os
import threading

# 📌 CONFIGURATION TELEGRAM
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise Exception("API_ID, API_HASH ou BOT_TOKEN manquants!")

# 📌 ID DES GROUPES & CANAUX
STOCKAGE_FILM = -1002314286062  
GROUPE_FILMS = "NetCloud_Films"  

# 🔹 Correspondance des genres avec les sujets du groupe
GENRE_TO_THREAD = {"Action": 5, "Drame": 6, "Science-Fiction": 7, "Animation": 12, 
    "Policier": 13, "Documentaire": 14, "Thriller": 10, "Aventure": 8, 
    "Horreur": 11, "Comédie": 4, "Fantastique": 9}

# 📊 CONFIGURATION GOOGLE SHEETS
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "gestion-films-453309-bd7ac526c981.json"
gc = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE))
sheet = gc.open("liste film NETCLOUD TOUS").sheet1

# 📌 Initialisation du bot Telegram
client = TelegramClient("gestion_netcloud", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# 🔍 Mémoire des films en attente de vidéo
pending_movies = {}
video_queue = []

def normalize_title(title):
    title = unidecode.unidecode(title)
    title = re.sub(r"[^a-zA-Z0-9 ]", "", title)
    return re.sub(r"\s+", " ", title.strip().lower())

def get_next_row():
    records = sheet.get_all_records(expected_headers=["N°", "Titre du film", "Lien Telegram", "PUBLIÉ", "Genre"])
    return len(records) + 1

app = Flask(__name__)

@app.route('/')
def home():
    return "NetCloud Bot API is running!", 200

@client.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond("👋 Bienvenue sur le bot NetCloud Films ! Envoyez un film dans le bon format pour qu'il soit publié.")
    print("[LOG] Commande /start exécutée par", event.sender_id)

@client.on(events.NewMessage(chats=STOCKAGE_FILM))
async def handle_new_movie(event):
    global pending_movies, video_queue
    
    print("[LOG] Nouveau message reçu dans le stockage de films")

    if event.photo and event.text:
        print("[LOG] Message avec photo détecté")
        message_text = event.raw_text.strip()
        lines = message_text.split("\n")
        
        if len(lines) < 2 or "Genre - " not in lines[1]:
            print("[LOG] Format du message incorrect, ignoré")
            return
        
        title = normalize_title(lines[0].replace("Titre - ", ""))
        genre = lines[1].replace("Genre - ", "").strip().capitalize()
        
        if genre not in GENRE_TO_THREAD:
            print(f"[LOG] Genre '{genre}' non reconnu, ignoré")
            return
        
        thread_id = GENRE_TO_THREAD[genre]
        sent_message = await client.send_file(
            f"@{GROUPE_FILMS}", event.photo, caption=message_text, reply_to=thread_id
        )
        pending_movies[title] = {"genre": genre, "message_id": sent_message.id}
        
        next_row = get_next_row()
        sheet.update(f"B{next_row}:E{next_row}", [[title, f"https://t.me/{GROUPE_FILMS}/{sent_message.id}", "✅", genre]])
        
        # Ajout automatique d'une ligne vide en dessous
        sheet.insert_row(["", "", "", "", ""], next_row + 1)

        print(f"[LOG] Film '{title}' publié et enregistré dans Google Sheets avec une ligne vide en dessous")

        for video in video_queue[:]:
            if normalize_title(video["text"]) == title:
                await send_video(video["event"], title)
                video_queue.remove(video)
                break  
    
    elif event.video or event.document:
        print("[LOG] Message avec vidéo ou fichier détecté")
        caption_text = event.text.strip() if event.text else ""
        
        if caption_text == "_" or caption_text == "":
            if pending_movies:
                caption_text = list(pending_movies.keys())[-1]
        
        title_found = next((title for title in pending_movies.keys() if normalize_title(caption_text) == title), None)
        
        if title_found:
            await send_video(event, title_found)
        else:
            print("[LOG] Vidéo ou fichier mis en attente")
            video_queue.append({"event": event, "text": caption_text})

async def send_video(event, title):
    global pending_movies
    
    try:
        print(f"[LOG] Envoi de la vidéo pour '{title}'")
        data = pending_movies[title]
        sent_video = await client.send_file(
            f"@{GROUPE_FILMS}", event.media, caption=event.text.replace("_", ""), reply_to=data["message_id"]
        )
        
        records = sheet.get_all_records(expected_headers=["N°", "Titre du film", "Lien Telegram", "PUBLIÉ", "Genre"])
        for i, record in enumerate(records, start=2):
            if f"https://t.me/{GROUPE_FILMS}/{data['message_id']}" in record["Lien Telegram"]:
                sheet.update_cell(i, 3, f"https://t.me/{GROUPE_FILMS}/{sent_video.id}")
                break

        del pending_movies[title]
        print(f"[LOG] Vidéo ou fichier pour '{title}' envoyé et mis à jour dans Google Sheets")
    except Exception as e:
        print(f"❌ [ERREUR] Problème lors de l'envoi de la vidéo ou fichier : {e}")

if __name__ == "__main__":
    print("✅ [LOG] Bot démarré...")
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()
    try:
        client.run_until_disconnected()
    except KeyboardInterrupt:
        print("❌ [LOG] Bot arrêté.")
        os._exit(0)
