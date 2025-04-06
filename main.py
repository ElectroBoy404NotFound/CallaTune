import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"
# os.environ['LOG_LEVEL_DEBUG'] = "1"
# os.environ['LOG_LEVEL_VERBOSE_DEBUG'] = "1"

from lib.sim900a import SIM900A
from lib.logger import Logger
import re
import pygame
# from RealtimeTTS import TextToAudioStream, GTTSEngine
import time
from datetime import datetime

import importlib
def load_data():
    # Import or reload the module containing the dictionary
    import song_data
    importlib.reload(song_data)
    return song_data.songs  # Access the dictionary from the module

logger = Logger("CallaTune")

pattern_menu = r".*\bmenu\s*(\d+)\b.*"
pattern_song = r".*\bsong\s*(\d+)\b.*"

songs = load_data()

song_menu = []

current_song = songs[1]

music_playing = False

def on_music_end(gsm):
    gsm.hang_up()
    gsm.sendSMS_txtmode_lastcaller("Thank you for listening! Use \"menu\" to get list of songs and \"song\" to select a song.")

def play_music():
    global music_playing
    pygame.mixer.music.load(current_song[2])
    pygame.mixer.music.play()
    music_playing = True
def end_music():
    pygame.mixer.music.stop()

def get_menu_number(mstr):
    match = re.search(pattern_menu, mstr)
    if match:
        return int(match.group(1)) - 1
    return 0

def get_song_number(mstr):
    match = re.search(pattern_song, mstr)
    if match:
        return int(match.group(1))
    return 0

def build_song_list_with_pagination(triplet_dict, header, padding_length=2, max_length=154):
    entries = [f"{key}:{value[1]}" for key, value in triplet_dict.items()]
    
    pages = []
    footer_base = "Page {}/{}"
    header_footer_length = len(header) + len(footer_base.format(1, 1)) + 4  # +4 for \r\n\r\n
    padding = "\r\n" * padding_length
    max_body_length = max_length - header_footer_length - len(padding) * 2  # Space available for songs

    current_page_entries = []
    current_body_length = 0
    for entry in entries:
        entry_length = len(entry) + 2  # Account for \r\n
        if current_body_length + entry_length <= max_body_length:
            current_page_entries.append(entry)
            current_body_length += entry_length
        else:
            # Start a new page
            pages.append(current_page_entries)
            current_page_entries = [entry]
            current_body_length = entry_length

    # Add the last page
    if current_page_entries:
        pages.append(current_page_entries)

    # Generate final pages with headers, padding, and footers
    total_pages = len(pages)
    final_pages = []
    for i, page_entries in enumerate(pages, start=1):
        footer = f"Page {i}/{total_pages}"
        body = "\r\n".join(page_entries)
        page = f"{header}{padding}\r\n{body}{padding}\r\n{footer}".ljust(max_length)[:max_length]
        final_pages.append(page)

    return final_pages

def sms_callback(header, data, args):
    global current_song

    logger.debug(f"SMS From {header[0]} at {header[1]} with message ID {header[2]} and content \"{data}\"")

    gsm = args[0]
    data = data.lower()

    gsm.delete_sms(header[2])

    if "menu" in data:
        menu_no = get_menu_number(data)
        if menu_no >= len(song_menu):
            gsm.sendSMS_txtmode(header[0], "Invalid menu number!")
            return
        gsm.sendSMS_txtmode(header[0], song_menu[get_menu_number(data)])
    elif "song" in data:
        song_no = get_song_number(data)
        if song_no < 1 or song_no > len(songs):
            gsm.sendSMS_txtmode(header[0], "Invalid song number. Send \"menu\" to get available songs")
            return
        current_song = songs[song_no]
        gsm.sendSMS_txtmode(header[0], f"Selected song {song_no} ({current_song[1]})\r\nCall to listen to the song!")
    else:
        gsm.sendSMS_txtmode(header[0], f"Unknown! Please use \"menu\" to get list of songs and \"song\" to select song by number")

def phone_callback(data, args):
    gsm = args[0]
    now = datetime.now()
    formatted_time = now.strftime("%y/%m/%d,%H:%M:%S")

    if data[2] == 0:
        play_music()
        logger.debug(f"Answered call from {data[5]} at {formatted_time}")
    elif data[2] == 1:
        logger.debug(f"Held call from {data[5]} at {formatted_time}")
    elif data[2] == 4:
        logger.debug(f"Received call from {data[5]} at {formatted_time}")
    elif data[2] == 5:
        gsm.add_waiting_call()
        logger.debug(f"Added Waiting call from {data[5]} at {formatted_time}")
    elif data[2] == 6:
        end_music()
        logger.debug(f"End call from {data[5]} at {formatted_time}")
    return True

def main():
    global song_menu
    global music_playing
    global songs

    pygame.mixer.init()

    gsm = SIM900A('COM3', 9600)

    gsm.set_sms_callback(sms_callback, args=(gsm,))
    gsm.set_phone_callback(phone_callback, args=(gsm,))

    gsm.start_thread()

    song_menu = build_song_list_with_pagination(songs, "==Song List==")
    logger.info(f"Generated song menu")
    logger.debug(f"Song Menu: {song_menu}")

    logger.info(f"System Ready")

    while True:
        while music_playing:
            if not pygame.mixer.music.get_busy():  # Check if the music is no longer playing
                on_music_end(gsm)
                music_playing = False  # Exit the loop when the song ends
            time.sleep(0.3)
        updated_data = load_data()
        try:
            if updated_data != songs:
                logger.info(f"Song Menu updated")
                songs = updated_data
                song_menu = build_song_list_with_pagination(songs, "==Song List==")
                logger.debug(f"New song menu: {song_menu}")
        except SyntaxError:
            logger.error("Syntax error in song_data! Please check!")

if __name__ == "__main__":
    main()
