import keyring

OPEN_AI_KEY            = None, 
WHATSAPP_VERIFY_TOKEN  = None, 
WHATSAPP_ACCESS_TOKEN  = None
WHATSAPP_PHONE_ID      = None


def initEnv():
    global OPEN_AI_KEY, WHATSAPP_VERIFY_TOKEN, WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_ID
    OPEN_AI_KEY             = keyring.get_password('OPEN_AI_KEY', "MatchMX")
    WHATSAPP_VERIFY_TOKEN   = keyring.get_password('WHATSAPP_VERIFY_TOKEN', "MatchMX")
    WHATSAPP_ACCESS_TOKEN   = keyring.get_password('WHATSAPP_ACCESS_TOKEN', "MatchMX")
    WHATSAPP_PHONE_ID       = keyring.get_password('WHATSAPP_PHONE_ID', "MatchMX")


def databaseUrl():
    server       = 'mxdev'
    username     = server + 'py'
    password     = keyring.get_password(f'{username}@{server}', "MatchMX")
    server       = f'{server}.postgres.database.azure.com'
    port         = 5432
    mxdb         = 'matchmx'
    DATABASE_URL = f"postgresql://{username}:{password}@{server}:{port}/{mxdb}"
    return DATABASE_URL



