import serial
import threading
import time
import re
from . import logger

class SIM900A:
    __sms_callback = None
    __phone_callback = None
    __sms_params = None
    __phone_params = None
    __serial = None
    __block_thread = False
    __serial_thread = None

    __is_call_ongoing = False
    __last_caller = None

    __logger = logger.Logger("SIM900A")

    CALL_STATUS_ACTIVE = 0
    CALL_STATUS_HELD = 1
    CALL_STATUS_DIALING = 2
    CALL_STATUS_ALERTING = 3
    CALL_STATUS_INCOMING = 4
    CALL_STATUS_WAITING = 5
    CALL_STATUS_DISCONNECTED = 6

    CALL_DIRECTION_INCOMING = 0
    CALL_DIRECTION_OUTGOING = 1

    def __init__(self, com_port, baudrate):
        self.__logger.verbose_debug(f"Initializing SIM900A on {com_port} with baudrate {baudrate}")
        self.__serial = serial.Serial(port=com_port, baudrate=baudrate, timeout=1)

        self.__serial.write(b"AT+CLCC=1\r\n")
        if not self.__wait_for_char("OK"):
            self.__logger.warn("Failed to set CLCC mode")
        self.__serial.write(b"AT+CNMI=2,1,0,0,0\r\n")
        if not self.__wait_for_char("OK"):
            self.__logger.warn("Failed to set CNMI mode")
        self.__serial.write(b"AT+CMGF=1\r\n")
        if not self.__wait_for_char("OK"):
            self.__logger.warn("Failed to set CMGF mode")

    def set_sms_callback(self, smscallback, args=()):
        self.__sms_callback = smscallback
        self.__sms_params = args

    def set_phone_callback(self, phcallback, args=()):
        self.__phone_callback = phcallback
        self.__phone_params = args

    def start_thread(self):
        if self.__serial_thread is None:
            serial_thread = threading.Thread(target=self.__gsm_thread, args=(), daemon=True)
            serial_thread.start()

    def __CMTI_handler(self, data):
        self.__logger.verbose_debug(f"CMTI handler: {data}")

        match = re.search(r'(\d+)$', data)
        if not match:
            return
        
        sms = ""
        header = None
        last_digit = match.group(1)
        
        self.__serial.write(f"AT+CMGR={last_digit}\r\n".encode())
        while True:
            if self.__serial.in_waiting > 0:
                sms_data = self.__serial.readline().decode('utf-8').strip()
                if not sms_data:
                    continue
                if "AT+" in sms_data:
                    continue
                if "+CMGR: " in sms_data:
                    header = self.__decode_CMGR(sms_data)
                    if header:
                        header = header + (int(last_digit),)
                    else: 
                        header = (0, "", int(last_digit))
                    continue
                if "OK" in sms_data:
                    break
                sms = sms + sms_data + "\n"
            else:
                time.sleep(0.1)
        
        sms = sms[:-1]
        if not self.__sms_callback:
            self.__logger.warn("No SMS callback set, got {header}, {sms}")
            return
        self.__sms_callback(header, sms, self.__sms_params)

    def __CLCC_handler(self, data):
        self.__logger.verbose_debug(f"CLCC handler: {data}")
        dec_dat = self.__decode_CLCC(data)
        if not self.__phone_callback:
            self.__logger.warn("No phone callback set, got {dec_dat}")
            return
        
        ret = self.__phone_callback(dec_dat, self.__phone_params)

        if dec_dat[2] == 0:
            self.__is_call_ongoing = True
            self.__last_caller = dec_dat[5]
        elif dec_dat[2] == 6:
            self.__is_call_ongoing = False

        if ret and dec_dat[2] == 4:
            self.__answer_call()

    def __gsm_handler(self, data):
        self.__logger.verbose_debug(f"GSM handler: {data}")
        
        if "+CMTI:" in data and self.__sms_callback is not None:
            self.__CMTI_handler(data)
        elif "+CLCC: " in data and self.__phone_callback is not None:
            self.__CLCC_handler(data)

    def __gsm_thread(self):
        while True:
            while self.__block_thread:
                time.sleep(0.1)
            try:
                if self.__serial.in_waiting > 0:
                    data = self.__serial.readline().decode('utf-8').strip()
                    self.__logger.verbose_debug(f"Received: {data}")
                    self.__gsm_handler(data)
                else:
                    time.sleep(0.1)  # Avoid high CPU usage when no data is received
            except serial.SerialException as e:
                # Handle serial port errors (e.g., disconnection)
                self.__logger.error(f"Serial error: {e}")
                break
            except Exception as e:
                self.__logger.error(f"Unexpected error: {e}")
        self.__serial.close()
        self.__logger.error("Exiting serial reading thread.")

    def __decode_CLCC(self, string):
        self.__logger.verbose_debug(f"Decoding CLCC: {string}")
        clcc_pattern = r'\+CLCC: (\d+),(\d+),(\d+),(\d+),(\d+),"(.*?)",(\d+),"?"(.*?)"?'
        clcc_match = re.search(clcc_pattern, string)

        if clcc_match:
            idx = int(clcc_match.group(1))           # Call index
            direction = int(clcc_match.group(2))    # Direction
            status = int(clcc_match.group(3))       # Call status
            mode = int(clcc_match.group(4))         # Call mode
            multiparty = int(clcc_match.group(5))   # Multiparty state
            number = clcc_match.group(6)            # Phone number
            num_type = int(clcc_match.group(7))     # Number type
            alpha = clcc_match.group(8)             # Alphanumeric info (if any)

            self.__logger.verbose_debug(f"Decoded CLCC: {idx}, {direction}, {status}, {mode}, {multiparty}, {number}, {num_type}, {alpha}")
            return (idx, direction, status, mode, multiparty, number, num_type, alpha)

        self.__logger.warn(f"Failed to decode CLCC: {string}")
        self.__logger.verbose_debug(f"CLCC pattern: {clcc_pattern}")
        self.__logger.verbose_debug(f"CLCC match: {clcc_match}")
        return None
    
    def __decode_CMGR(self, str):
        match = re.search(r'"(\+?\d+)",.*,"([\d/]+,[\d:]+)', str)

        if match:
            phone_number = match.group(1)
            time = match.group(2)
            return (phone_number, time)

        return None

    def __answer_call(self):
        self.__wait_for_char("RING")
        self.__serial.write(b"ATA\r\n")
        self.__wait_for_char("OK")

    def __wait_for_char(self, char):
        while True:
            if self.__serial.in_waiting > 0:
                dat = self.__serial.readline().decode('utf-8').strip()
                self.__logger.verbose_debug(f"Waiting for {char}: {dat}")
                if char in dat:
                    break
                if "ERROR" in dat:
                    self.__logger.verbose_debug(f"GSM responded with ERROR!")
                    return False
        self.__logger.verbose_debug(f"In queue {self.__serial.in_waiting} bytes")
        self.__logger.verbose_debug(f"Read lines: {self.__serial.readlines()}")
        self.__logger.verbose_debug(f"Waiting for {char} done")
        return True

    def sendSMS_txtmode_lastcaller(self, message):
        self.sendSMS_txtmode(self.__last_caller, message)

    def sendSMS_txtmode(self, number, message):
        self.__block_thread = True

        self.__serial.write(b'AT+CMGF=1\r\n')
        self.__wait_for_char("OK")
        self.__serial.write(f'AT+CMGS="{number}"\r\n'.encode())
        self.__wait_for_char(">")
        self.__serial.write(f'{message}\r\n'.encode())
        self.__wait_for_char(">")
        self.__serial.write(b'\x1A')
        self.__wait_for_char("OK")

        self.__block_thread = False

    def delete_sms(self, sms_no):
        self.__block_thread = True
        self.__serial.write(f'AT+CMGD={sms_no}\r\n'.encode())
        self.__wait_for_char("OK")
        self.__block_thread = False

    def get_call_status(self):
        return self.__is_call_ongoing

    def hang_up(self):
        if self.__is_call_ongoing:
            self.__serial.write(b"ATH\r\n")
            self.__wait_for_char("OK")
    
    def add_waiting_call(self):
        self.__serial.write(b"AT+CHLD=2\r\n")
        self.__wait_for_char("OK")
        self.__serial.write(b"AT+CHLD=3\r\n")
        self.__wait_for_char("OK")