import serial
import threading
import time
import re
import pygame

from RealtimeTTS import TextToAudioStream, GTTSEngine

def decode_CLCC(data):
    clcc_pattern = r'\+CLCC: (\d+),(\d+),(\d+),(\d+),(\d+),"(.*?)",(\d+),"?"(.*?)"?'
    clcc_match = re.search(clcc_pattern, data)

    if clcc_match:
        # Parse the CLCC fields
        idx = int(clcc_match.group(1))           # Call index
        direction = int(clcc_match.group(2))    # Direction
        status = int(clcc_match.group(3))       # Call status
        mode = int(clcc_match.group(4))         # Call mode
        multiparty = int(clcc_match.group(5))   # Multiparty state
        number = clcc_match.group(6)            # Phone number
        num_type = int(clcc_match.group(7))     # Number type
        alpha = clcc_match.group(8)             # Alphanumeric info (if any)

        # Display the parsed fields
        # print(f"Call Index: {idx}")
        # print(f"Direction: {direction} ('1' for Incoming, '0' for Outgoing)")
        # print(f"Status: {status} (6 = Disconnected)")
        # print(f"Mode: {mode} ('0' for Voice, etc.)")
        # print(f"Multiparty: {multiparty} ('0' for Single Call)")
        # print(f"Number: {number}")
        # print(f"Number Type: {num_type} ('145' = International)")
        # print(f"Alpha Info: {alpha}")

        return (idx, direction, status, mode, multiparty, number, num_type, alpha)
    else:
        print("No valid +CLCC response found.")

    return None

def play_music(song):
    print(song)
    if song == 0:
        pygame.mixer.music.load("song_0.mp3")
        print("Song 0 loaded")
    if song == 1:
        pygame.mixer.music.load("song_1.mp3")
        print("Song 1 loaded")
    if song == 2:
        pygame.mixer.music.load("song_2.mp3")
        print("Song 2 loaded")
    pygame.mixer.music.play()

def stop_music():
    pygame.mixer.music.stop()

def decode_cmgr(str):
    match = re.search(r'"(\+?\d+)",.*,"([\d/]+,[\d:]+)', str)

    if match:
        phone_number = match.group(1)  # First group is the phone number
        time = match.group(2)          # Second group is the date and time
        # print("Phone Number:", phone_number)
        # print("Time:", time)
        return (phone_number, time)
    else:
        print("No match found!")

MUSIC_END_EVENT = pygame.USEREVENT + 1
pygame.mixer.music.set_endevent(MUSIC_END_EVENT)

def sendSMS(number, message, ser):
    ser.write(f'AT+CMGS="{number}"\r\n'.encode())
    time.sleep(0.5)
    ser.write(f'{message}\r\n'.encode())
    ser.write(b'\x1A')

block_thread = False

def music_ended(ser):
    global block_thread
    block_thread = True
    engine = GTTSEngine() # replace with your TTS engine
    stream = TextToAudioStream(engine)
    stream.feed("Thank you! Please call again to replay and SMS to change music")
    stream.play()
    ser.write(b"AT+CLCC\r\n")
    caller = ""
    while True:
        if ser.in_waiting > 0:
            call_dat = ser.readline().decode('utf-8').strip()
            print(call_dat)
            if not call_dat:
                continue
            if "AT+" in call_dat:
                continue
            if "+CLCC: " in call_dat:
                print("FOUND YAA")
                caller = call_dat
                continue
            if "OK" in call_dat:
                break
            # print(sms)
        else:
            time.sleep(0.1)
    parsed_caller = decode_CLCC(caller)
    print(parsed_caller)
    if parsed_caller is None:
        block_thread = False
        return
    time.sleep(0.1)
    ser.write(b"ATH\r\n")
    time.sleep(0.4)
    sendSMS(parsed_caller[5], "Thank you for listning! Please message menu to get available options.", ser)
    block_thread = False

def song_changed(song):
    pass

song = 0
def handle_gsm(data, ser):
    global block_thread
    global song
    if "+CMTI: " in data:
        match = re.search(r'(\d+)$', data)
        if match:
            sms = ""
            header = ""
            last_digit = match.group(1)
            print(last_digit)
            ser.write(f"AT+CMGR={last_digit}\r\n".encode())
            while True:
                if ser.in_waiting > 0:
                    sms_data = ser.readline().decode('utf-8').strip()
                    if not sms_data:
                        continue
                    if "AT+" in sms_data:
                        continue
                    if "+CMGR: " in sms_data:
                        header = decode_cmgr(sms_data)
                        continue
                    if "OK" in sms_data:
                        break
                    sms = sms + sms_data + "\n"
                    # print(sms)
                else:
                    time.sleep(0.1)
            print(sms)
            print(header)

            time.sleep(0.3)
            if "menu" in sms.lower():
                ser.write(f'AT+CMGS="{header[0]}"\r\n'.encode())
                time.sleep(1)
                ser.write(f'===Song menu===\r\n'.encode())
                time.sleep(0.1)
                ser.write(f'1   - Nijamaa Kalaa (Lucky Baskhar)\r\n'.encode())
                time.sleep(0.1)
                ser.write(f'2   - Aa Rojulu Malli Raavu (Committee Kurrollu)\r\n'.encode())
                time.sleep(0.1)
                ser.write(f'3   - Pedave Palikina (Nani)\r\n'.encode())
                time.sleep(0.1)
                ser.write(f'Send song followed by the number next to it to select\r\n'.encode())
                time.sleep(0.1)
                ser.write(b'\x1A')
                # time.sleep(1)
                # ser.write(b"\r\n")
                # time.sleep(0.1)
            elif "song 1" in sms.lower():
                ser.write(f'AT+CMGS="{header[0]}"\r\n'.encode())
                time.sleep(1)
                ser.write(f'Now playing Nijamaa Kalaa (Lucky Baskhar)\r\n'.encode())
                time.sleep(0.1)
                ser.write(b'\x1A')
                song = 0
                song_changed(song)
            elif "song 2" in sms.lower():
                ser.write(f'AT+CMGS="{header[0]}"\r\n'.encode())
                time.sleep(1)
                ser.write(f'Now playing Aa Rojulu Malli Raavu (Committee Kurrollu)\r\n'.encode())
                time.sleep(0.1)
                ser.write(b'\x1A')
                song = 1
                song_changed(song)
            elif "song 3" in sms.lower():
                ser.write(f'AT+CMGS="{header[0]}"\r\n'.encode())
                time.sleep(1)
                ser.write(f'Now playing Pedave Palikina (Nani)\r\n'.encode())
                time.sleep(0.1)
                ser.write(b'\x1A')
                song = 2
                song_changed(song)
            else:
                ser.write(f'AT+CMGS="{header[0]}"\r\n'.encode())
                time.sleep(1)
                ser.write(f'I donno what you said :(\r\n'.encode())
                time.sleep(0.1)
                ser.write(b'\x1A')
            time.sleep(1)
            ser.write(f"AT+CMGD={last_digit}\r\n".encode())
            print("Okie!")
    if "+CLCC: " in data:
        dec_dat = decode_CLCC(data)
        # print(dec_dat[2])
        if dec_dat[2] == 4:
            ser.write(b'ATA\r\n')
            print(f"Answered call from {dec_dat[5]}")
        # if dec_dat[2] == 5:
        #     ser.write(b'ATA\r\n')
        #     print(f"Answered waiting call from {dec_dat[5]}")
        if dec_dat[2] == 0:
            print(f"Now on going {dec_dat[5]}")
            play_music(song)
        if dec_dat[2] == 6:
            stop_music()
            print(f"End call from {dec_dat[5]}")

def read_from_serial(ser):
    """Thread function to continuously read data from the serial port."""
    while True:
        while block_thread:
            time.sleep(0.1)
        try:
            if ser.in_waiting > 0:  # Check if there's data to read
                data = ser.readline().decode('utf-8').strip()
                print(f"Received: {data}")
                handle_gsm(data, ser)
            else:
                time.sleep(0.1)  # Avoid high CPU usage when no data is received
        except serial.SerialException as e:
            print(f"Serial error: {e}")
            break
        except Exception as e:
            print(f"Unexpected error: {e}")
    print("Exiting serial reading thread.")

def main():
    pygame.mixer.init()
    pygame.mixer.music.set_volume(0.7)

    try:
        # Open COM4 at 9600 bps
        ser = serial.Serial(port='COM4', baudrate=9600, timeout=1)
        print(f"Successfully opened {ser.port}")
        
        ser.write(b"AT+CLCC=1\r\n")
        time.sleep(1)
        ser.write(b"AT+CNMI=2,1,0,0,0\r\n")
        time.sleep(1)
        ser.write(b"AT+CMGF=1\r\n")

        # Start the serial reading thread
        serial_thread = threading.Thread(target=read_from_serial, args=(ser,), daemon=True)
        serial_thread.start()

        # Main thread can do other tasks
        print("Press Ctrl+C to exit the program.")
        was_busy = False
        while True:
            if not pygame.mixer.music.get_busy():
                if was_busy:
                    music_ended(ser)
                    was_busy = False
                    print("Okie!!! Finished!!")
            else:
                if not was_busy:
                    was_busy = True
    except serial.SerialException as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("Exiting program.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print(f"Closed {ser.port}")

if __name__ == "__main__":
    main()
