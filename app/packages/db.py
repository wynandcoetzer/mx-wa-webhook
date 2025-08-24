import asyncpg, json, re

userStates = {}

step             = 0

_pg              = None

def init_global(pg):
    global _pg, _input_maps
    _pg          = pg

#def get_pg():
#    if _pg is None:
#        raise RuntimeError("PG not initialized yet")
#    return _pg


# ------------- get user info from cache. If not in cache, retrieve from DB -----
async def getUser(phone):

    if phone in userStates.keys():
        user  =  userStates[phone]
        return user

    # not in cache - retrieve from DB
    row  = await _pg.fetchrow(
                '''
                SELECT "Id", "FirstName", "LastName", "PhoneNumber", "Email", "BrokerApp"
                FROM exchange."Users"
                WHERE "CallCode" || CASE WHEN Left("PhoneNumber", 1) <> '0' THEN "PhoneNumber"
            	                         ELSE SubString("PhoneNumber", 2, 20) END = @tel
                ORDER BY "Id"
                LIMIT 1
                ''',
                {"tel": phone}
            )
    #print("getUser row =", row)
    if row:
        user =  dict(row) | {'tel_str': phone}
    else:
        user = None
    return user

async def logChat(phone, ask, reply):
    params     = {'phone': phone, 'ask': ask, 'reply': reply}
    sql       = """
        INSERT INTO logs."WhatsApp" ("Phone", "Ask", "Reply")
        VALUES (@phone, @ask, @reply);
        """
    ret   = await _pg.execute(sql, params)
    return ret


# --------- enter user in cache ------------------
def setUser(phone, user):
    userStates[phone] = user


def safe_json_loads(s):
    try:
        return json.loads(s)
    except json.JSONDecodeError as e:
        return None  # or return {} or [] depending on your needs
    except TypeError as e:
        return None    


# ---------- retrieve user's entities
async def getEntities(crop_str, params):
    if crop_str in ('cattle', 'sheep', 'goat'):
        qGetEntities  = """
            SELECT
                json_object_agg(be."Name", be."Id")::json AS entities
            FROM exchange."BulkEntityUser" as beu 
            INNER JOIN exchange."BulkEntity" as be 
                ON be."Id" = beu."BulkEntityId"
            INNER JOIN exchange."Users" as u 
                ON u."Id" = beu."UserId" 
            WHERE beu."UserId" = @userId AND
                beu."Sell"     
            """
    else:
        qGetEntities  = """
            SELECT
                json_object_agg(be."Name", be."Id")::json AS entities
            FROM exchange."BulkEntityUser" as beu 
            INNER JOIN exchange."BulkEntity" as be 
                ON be."Id" = beu."BulkEntityId"
            INNER JOIN exchange."Users" as u 
                ON u."Id" = beu."UserId" 
            WHERE beu."UserId" = @userId AND
                beu."Sell"     
            """
    row      = await _pg.fetchrow(qGetEntities, params)
    #print("getEntities row =", row, ", dict(row) =", dict(row))
    entities = dict(row)['entities']
    if entities:
        return json.loads(entities)
    else:
        return None

# ------- convert named params to positional paarms required by asyncpg ----
# example:
#      sql    = """
#               SELECT * FROM orders
#               WHERE user_id = :uid OR created_by = :uid
#               AND status = :status"""
#      params = {"uid": 42, "status": "pending"}
#      sql_conv, args = sql_named(sql, params)
#      rows = await conn.fetch(sql_conv, *args)
def sql_named(sql: str, params: dict):
    """
    Convert :named parameters to asyncpg $1, $2 format.
    Reuses the same placeholder for repeated names.
    """
    pattern = re.compile(r"@([a-zA-Z_][a-zA-Z0-9_]*)")
    name_to_index = {}
    ordered_params = []

    def repl(match):
        name = match.group(1)
        if name not in params:
            raise KeyError(f"Missing parameter: {name}")
        if name not in name_to_index:
            name_to_index[name] = len(name_to_index) + 1
            ordered_params.append(params[name])
        return f"${name_to_index[name]}"

    sql_conv = pattern.sub(repl, sql)
    return sql_conv, ordered_params


class pgDB:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def fetch(self, sql: str, params: dict):
        sql_conv, args = sql_named(sql, params)
        async with self.pool.acquire() as conn:
            return await conn.fetch(sql_conv, *args)

    async def execute(self, sql: str, params: dict):
        sql_conv, args = sql_named(sql, params)
        async with self.pool.acquire() as conn:
            return await conn.execute(sql_conv, *args)

    async def fetchrow(self, sql: str, params: dict):
        sql_conv, args = sql_named(sql, params)
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(sql_conv, *args)

    async def fetchval(self, sql: str, params: dict):
        sql_conv, args = sql_named(sql, params)
        async with self.pool.acquire() as conn:
            return await conn.fetchval(sql_conv, *args)

