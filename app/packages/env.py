#import keyring
import os

OPEN_AI_KEY            = None, 
WHATSAPP_VERIFY_TOKEN  = None, 
WHATSAPP_ACCESS_TOKEN  = None
WHATSAPP_PHONE_ID      = None

def initEnv():
    print("=====> initEnv")
    global OPEN_AI_KEY, WHATSAPP_VERIFY_TOKEN, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_ID
    OPEN_AI_KEY             = os.environ.get('OPEN_AI_KEY')
    WHATSAPP_VERIFY_TOKEN   = os.environ.get('WHATSAPP_VERIFY_TOKEN')
    WHATSAPP_ACCESS_TOKEN   = os.environ.get('WHATSAPP_ACCESS_TOKEN')
    WHATSAPP_PHONE_ID       = os.environ.get('WHATSAPP_PHONE_ID')
    print("WHATSAPP_PHONE_ID =", WHATSAPP_PHONE_ID)

obsolete = """
    def initEnv():
        global OPEN_AI_KEY, WHATSAPP_VERIFY_TOKEN, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_ID
        OPEN_AI_KEY             = keyring.get_password('OPEN_AI_KEY', "MatchMX")
        WHATSAPP_VERIFY_TOKEN   = keyring.get_password('WHATSAPP_VERIFY_TOKEN', "MatchMX")
        WHATSAPP_ACCESS_TOKEN   = keyring.get_password('WHATSAPP_ACCESS_TOKEN', "MatchMX")
        WHATSAPP_PHONE_ID       = keyring.get_password('WHATSAPP_PHONE_ID', "MatchMX")
    """

server               = 'mxdev'
username             = server + 'py'

def databaseUrl():
    servename    = 'mxdev'                     #os.environ.get('DB_SERVER')                              
    username     = servename + 'py'
    password     = os.environ.get('ALARM')
    #userpw       = f'{username}@{server}                                   #keyring.get_password(f'{username}@{server}', "MatchMX")
    server       = f'{servename}.postgres.database.azure.com'
    port         = 5432
    mxdb         = 'matchmx'
    DATABASE_URL = f"postgresql://{username}:{password}@{server}:{port}/{mxdb}"
    print("DATABASE_URL", DATABASE_URL)
    return DATABASE_URL



