"""
protocol.py -- LAPISAN PROTOKOL (ngikut dari kelompok 9, server kamii)

Semua konstanta di sini adalah "kontrak" dengan server: nama layanan, tipe pesan,
nilai status/action. Dikomunikasikan secara langsung dan lewat WA dengan kelompok 9, 
jangan diubah sendiri !

"""
import json

ENCODING = "utf-8"
DEFAULT_PORT = 5001
MAX_MESSAGE_BYTES = 64 * 1024      

#  Nama layanan (huruf kecil, sesuai server) 
CHAR_COUNT = "char_count"
WORD_COUNT = "word_count"
REVERSE = "reverse"
REMOVE_VOWELS = "remove_vowels"
MATRIX = "matrix_3x3"
SERVICES = [CHAR_COUNT, WORD_COUNT, REVERSE, REMOVE_VOWELS, MATRIX]

#  Tipe pesan 
SERVER_HELLO = "server_hello"          
REQUEST = "request"                    
RESPONSE = "response"                  
ACK = "ack"                            
ACK_RESULT = "ack_result"              
STATUS_REQUEST = "status_request"      
SERVER_STATUS = "server_status"        
SERVER_SHUTDOWN = "server_shutdown"    
ERROR = "error"                        

#  Nilai field `status` pada response 
STATUS_OK = "ok"
STATUS_SERVICE_DISABLED = "service_disabled"

#  Nilai field `action` pada ack_result 
ACTION_ACCEPTED = "accepted"
ACTION_SERVICE_DISABLED = "service_disabled"


def encode(msg: dict) -> bytes:
    return (json.dumps(msg, ensure_ascii=False) + "\n").encode(ENCODING)