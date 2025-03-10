import gspread
from telethon import TelegramClient, events
from oauth2client.service_account import ServiceAccountCredentials
import asyncio
import re
import unidecode
import os

# 📌 CONFIGURATION TELEGRAM
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not API_ID or not API_HASH or not BOT_TOKEN:
    raise Exception("❌ API_ID, API_HASH ou BOT_TOKEN manquants! Vérifie tes variables d'environnement.")

# 📌 ID DES GROUPES & CANAUX
STOCKAGE_FILM = -1002314286062  
GROUPE_FILMS = "NetCloud_Films"  

# 🔹 Correspondance des genres avec les sujets du groupe
GENRE_TO_THREAD = {
    "Action": 5, "Drame": 6, "Science-Fiction": 7, "Animation": 12, 
    "Policier": 13, "Documentaire": 14, "Thriller": 10, "Aventure": 8, 
    "Horreur": 11, "Comédie": 4, "Fantastique": 9
}

# 📊 CONFIGURATION GOOGLE SHEETS
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS_FILE = "gestion-films-453309-bd7ac526c981.json"

if not os.path.exists(CREDS_FILE):
    raise Exception(f"❌ Fichier {CREDS_FILE} introuvable. Vérifie ton déploiement sur Render!")

gc = gspread.authorize(ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPE))
sheet = gc.open("liste film NETCLOUD TOUS").sheet1

# 📌 Initialisation du bot Telegram
client = TelegramClient("gestion_netcloud", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# 🔍 Mémoire des films en attente de vidéo
pending_movies = {}
video_queue = []

def normalize_title(title):
    """ Nettoie et normalise le titre pour éviter les erreurs de correspondance """
    title = unidecode.unidecode(title)
    title = re.sub(r"[^a-zA-Z0-9 ]", "", title)
    return re.sub(r"\s+", " ", title.strip().lower())

def get_next_row():
    """ Trouve la prochaine ligne disponible et ajoute des lignes si nécessaire """
    records = sheet.get_all_records(expected_headers=["N°", "Titre du film", "Lien Telegram", "PUBLIÉ", "Genre"])
    return len(records) + 1

@client.on(events.NewMessage(chats=STOCKAGE_FILM))
async def handle_new_movie(event):
    global pending_movies, video_queue

    if event.photo and event.text:
        message_text = event.raw_text.strip()
        lines = message_text.split("\n")
        
        if len(lines) < 2 or "Genre - " not in lines[1]:
            return
        
        title = normalize_title(lines[0].replace("Titre - ", ""))
        genre = lines[1].replace("Genre - ", "").strip().capitalize()
        
        if genre not in GENRE_TO_THREAD:
            return
        
        thread_id = GENRE_TO_THREAD[genre]
        sent_message = await client.send_file(
            f"@{GROUPE_FILMS}", event.photo, caption=message_text, reply_to=thread_id
        )
        pending_movies[title] = {"genre": genre, "message_id": sent_message.id}
        
        next_row = get_next_row()
        sheet.update(f"B{next_row}:E{next_row}", [[title, f"https://t.me/{GROUPE_FILMS}/{sent_message.id}", "✅", genre]])
        
        for video in video_queue[:]:
            if normalize_title(video["text"]) == title:
                await send_video(video["event"], title)
                video_queue.remove(video)
                break  

    elif event.video:
        caption_text = event.text.strip() if event.text else ""
        
        if caption_text == "_" or caption_text == "":
            if pending_movies:
                caption_text = list(pending_movies.keys())[-1]
        
        title_found = next((title for title in pending_movies.keys() if normalize_title(caption_text) == title), None)
        
        if title_found:
            await send_video(event, title_found)
        else:
            video_queue.append({"event": event, "text": caption_text})

async def send_video(event, title):
    global pending_movies

    try:
        data = pending_movies[title]
        sent_video = await client.send_file(
            f"@{GROUPE_FILMS}", event.video, caption=event.text.replace("_", ""), reply_to=data["message_id"]
        )
        
        records = sheet.get_all_records(expected_headers=["N°", "Titre du film", "Lien Telegram", "PUBLIÉ", "Genre"])
        for i, record in enumerate(records, start=2):
            if f"https://t.me/{GROUPE_FILMS}/{data['message_id']}" in record["Lien Telegram"]:
                sheet.update_cell(i, 3, f"https://t.me/{GROUPE_FILMS}/{sent_video.id}")
                break

        del pending_movies[title]
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi de la vidéo : {e}")

if __name__ == "__main__":
    print("✅ Bot lancé sur Render...")
    try:
        client.run_until_disconnected()
    except KeyboardInterrupt:
        print("❌ Bot arrêté.")
        os._exit(0)
