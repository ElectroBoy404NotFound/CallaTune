import serial
import threading
import time
import re

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

    def __init__(self, com_port, baudrate):
        self.__serial = serial.Serial(port=com_port, baudrate=baudrate, timeout=1)

        self.__serial.write(b"AT+CLCC=1\r\n")
        self.__wait_for_char("OK")
        self.__serial.write(b"AT+CNMI=2,1,0,0,0\r\n")
        self.__wait_for_char("OK")
        self.__serial.write(b"AT+CMGF=1\r\n")
        self.__wait_for_char("OK")

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
        self.__sms_callback(header, sms, self.__sms_params)

    def __CLCC_handler(self, data):
        dec_dat = self.__decode_CLCC(data)
        ret = self.__phone_callback(dec_dat, self.__sms_params)

        if dec_dat[2] == 0:
            self.__is_call_ongoing = True
            self.__last_caller = dec_dat[5]
        elif dec_dat[2] == 6:
            self.__is_call_ongoing = False

        if ret and dec_dat[2] == 4:
            self.__answer_call()

    def __gsm_handler(self, data):
        # print(type(self))
        # print(data)
        
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
                    # print(f"Received: {data}")
                    self.__gsm_handler(data)
                else:
                    time.sleep(0.1)  # Avoid high CPU usage when no data is received
            except serial.SerialException as e:
                print(f"Serial error: {e}")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
        print("Exiting serial reading thread.")

    def __decode_CLCC(self, string):
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

            return (idx, direction, status, mode, multiparty, number, num_type, alpha)

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
                if char in dat:
                    break

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

    def __encode_pdu(self, number, message):
        """Encode the phone number and message into a PDU format."""
        # Phone number encoding (add zero-padding if needed)
        if number.startswith("+"):
            number = number[1:]
        length = len(number)
        if length % 2 != 0:
            number += "F"
        encoded_number = ''.join([number[i+1] + number[i] for i in range(0, len(number), 2)])
        encoded_number = f"91{encoded_number}"  # 91 indicates international format

        # Message encoding (7-bit GSM default alphabet)
        encoded_message = ''.join([f"{ord(c):02X}" for c in message])

        # Calculate lengths
        tpdu_length = len(encoded_message) // 2
        return f"00{len(number)//2:02X}{encoded_number}0000A7{tpdu_length:02X}{encoded_message}"

    def sendSMS_pdumode(self, number, message):
        self.__block_thread = True

        self.__serial.write(b"AT+CMGF=0\r\n")
        self.__wait_for_char("OK")
        
        pdu_message = self.__encode_pdu(number, message)
        length = len(pdu_message) // 2
        
        print(pdu_message)

        self.__serial.write(f"AT+CMGS={length}\r\n".encode())
        self.__wait_for_char(">")
        self.__serial.write(f"{pdu_message}\x1A".encode())  # \x1A is the Ctrl+Z character
        # self.__wait_for_char("OK")
        
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