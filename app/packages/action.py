import json, re
from . import db

_pg              = None
_input_maps      = None

def init_global(pg, input_maps):
    global _pg, _input_maps
    _pg          = pg
    _input_maps  = input_maps



# ------ handle a DB result that may be empty, singular or multiple values
def parseChoices(tel_str, choices):
    if not choices:
        return {'invalid': True}
    elif len(choices) == 1:
        db.step     = 165
        #print("parseChoices choices =", choices, ", choices keys =", choices.keys(), ", choices.values =", choices.values())
        entity    = list(choices.keys())[0]
        eid       = choices[entity]
        return {'invalid': False, 'Id': eid, 'entity': entity}
    else:
        # create a {sequence: choice} dict and append to global input_maps for tell_str
        # also create an enumerated choices string for ChatGPT 
        entity_map           = {str(i+1): e for i, e in enumerate(choices.keys())}
        _input_maps[tel_str] = entity_map
        choices              = "\n".join([f"{num} - {name}" for num, name in entity_map.items()])
        return {'invalid': False, 'Id': None, 'choices': choices}

# ---- parse age function values into Age(Id) ---
async def parseAge(crop_str, age_str, params = {}):
    if not age_str:
        return params
    #print('crop_str =', crop_str, 'age_str =', age_str)
    ageIds  = {'cattle': {7:1, 8:2, 24:3, 30:4, 36:5, 42:6, 48:7},
               'sheep':  {5:11, 7:12, 12:13, 24:14, 36:15, 60:16}}
    p   = re.match(r'^([0-9]+) (tooth|teeth|year|years|month|months])', age_str.strip().lower())
    if not p:
        print("\nRE error - no match")
        retry_str     = f'INVALID: age = {age_str} (not found in DB, please ask user again)'
        return params, retry_str
    else:
        animals   = {'cattle': 1, 'sheep': 2, 'goat': 3}     # TODO handle teeth  and goats
        params['animalId']  = animals.get(crop_str, 0)
        num  = int(p.group(1))
        unit = p.group(2)
        #print("num =", num, "unit =", unit)
        if unit[0] == 'y':
            num    = round(num * 12)
        ids   = ageIds[crop_str]
        aId   = 0
        for i in ids.keys():
            if num <= i:
                aId  = ids[i]
                break
        if aId == 0:
            aId   = {'cattle': 8, 'sheep': 17}[crop_str]
        params['ageId'] = aId
        #print('parseAge params =', str(params))
        return params, ''

async def parseCropTownAge(user, crop_str, town_str, age_str, params={}):
    if crop_str in ('cattle', 'sheep', 'goat'):
        params, retry_str  = await parseAge(crop_str, age_str, params)
        if retry_str:
            return params, retry_str

    # validate crop and town - crop is later ignored if animals
    qValidateCropTown  = """
        SELECT
            CASE WHEN townIds1 IS Not Null THEN townIds1
                ELSE "townIds" END                          AS "townIds",
            CASE WHEN cropIds1 IS Not Null THEN cropIds1
                ELSE "cropIds" END                          AS "cropIds"
        FROM
            (SELECT
                (SELECT
                    json_object_agg("Name", "Id" ORDER BY "Name")
                FROM exchange."DeliveryPoints" as dp
                WHERE dp."LocationTypeId" = 9 AND 
                    dp."Town" iLIKE '%' || @town || '%')                      AS "townIds",
                (SELECT json_build_object("Name", "Id") 
                FROM exchange."DeliveryPoints"
                WHERE Lower(@town) = Lower("Town")
                ORDER BY "Id" LIMIT 1)                                         AS townIds1,
                (SELECT json_object_agg("Name", "Id" ORDER BY "Name") 
                FROM exchange."Crops" as cr
                WHERE cr."Name" iLIKE  '%' || @crop || '%')                    AS "cropIds",
                (SELECT json_build_object("Name", "Id") 
                FROM exchange."Crops"
                WHERE Lower(@crop) = Lower("Name")
                ORDER BY "Id" LIMIT 1)                                         AS cropIds1
            ) AS t   
        """
    row      = await _pg.fetchrow(qValidateCropTown, {'crop': crop_str.lower(), 'town': town_str})
    towns    = dict(row)['townIds']
    towns    = json.loads(towns) if towns else None
    crops    = dict(row)['cropIds']
    crops    = json.loads(crops) if crops else None
    #print("parseCropTownAge row =", dict(row), ", towns =", towns, ", crops =", crops)

    # validate town
    db.step                   = 171 
    parsed    = parseChoices(user['tel_str'], towns)
    #print("parsedChoices towns =", towns, ", parsed =", parsed)
    if parsed['invalid']:
        retry_str             = f'INVALID: town = {town_str} (not found in DB, please ask user again)'
        return params, retry_str
    elif parsed['Id']:
        params['townId']  = parsed['Id']
    else:
        retry_str             = "AMBIGUOUS: The town name you entered is ambiguous:\n" + parsed['choices'] + "\nReply with the number of your choice."
        return params, retry_str

    if crop_str in ('cattle', 'sheep', 'goat'):
        return params, ''
    else:
        # validate crop
        db.step               = 172 
        parsed    = parseChoices(user['tel_str'], crops)
        #print("parsedChoices crops =", crops, ", parsed =", parsed)
        if parsed['invalid']:
            retry_str         = f'INVALID: crop = {crop_str} (not found in DB, please ask user again)'
            return params, retry_str
        elif parsed['Id']:
            params['cropId']  = parsed['Id']
            return params, ''
        else:
            db.step               = 173
            retry_str         = "AMBIGUOUS: The crop name you entered is ambiguous:\n" + parsed['choices'] + "\nReply with the number of your choice."
            #print("parseCropTownAge retry_str =", retry_str, ", \nparams =", params)
            return params, retry_str

# parse all params for crop_offer GPT function
async def parseCropOffer(user, crop_str, town_str, price, quantity, age_str, entity):
    db.step            = 157
    params, retry_str  = await parseCropTownAge(user, crop_str, town_str, age_str)
    db.step            = 158
    if retry_str:
        return params, retry_str, ''
        
    params    = params | {'userId': user['Id'], 'price': price, 'quantity': quantity}
    #print("parseCropOffer params =", params)
    entities  = await db.getEntities(crop_str, params)
    db.step   = 159

    # use user selected entity that was replaced by inputs_map
    if entity and entity in entities:
        db.step               = 160
        params['entityId']    = entities[entity]        
        return params, '', entity

    # parse entities to determine (a) no entity, (b) one entity or (c) if the user must select from a list of entities
    parsed    = parseChoices(user['tel_str'], entities)
    db.step                   = 161 
    #print("parsedChoices entities =", entities, ", parsed =", parsed)
    if parsed['invalid']:
        return params, '', ''
    elif parsed['Id']:
        params['entityId']  = parsed['Id']
        return params, '', parsed['entity']
    else:
        retry_str             = "AMBIGUOUS: You are linked to the following entities:\n" + parsed['choices'] + "\nReply with the number of your choice."
        return params, retry_str, ''

async def getBestPrice(crop_str, params):
    if crop_str in ('cattle', 'sheep', 'goat'):
        qMeatBestPrice    = """
            SELECT
                /*
                "AnimalId", "AgeId",
                "DryPrice", "WetPrice", "transportPerKg", fee,
                "DryPrice" + "transportPerKg" + fee AS "dryPerKg",
                "WetPrice" + "transportPerKg" + fee AS "wetPerKg"
                */
                Min(Round("DryPrice" + "transportPerKg" + fee, 2)) AS "dryPerKg",
                Min(Round("WetPrice" + "transportPerKg" + fee, 2)) AS "wetPerKg"
            FROM
                (SELECT
                    bo."AnimalId", bo."AgeId",
                    bo."DryPrice", bo."WetPrice",
                    COALESCE(bo."DryPrice" * ppc."MeatFee", bo."WetPrice" * ppc."MeatFee") AS fee,
                    Round((Greatest(tt."PerKm" * tr."Kilos", tt."MinZAR") / (tl."Load" * a."Weight")), 2) AS "transportPerKg"
                FROM redmeat."MeatOrder" as bo 
                LEFT JOIN exchange."DeliveryPoints" as sdp 
                    ON sdp."Id" = @townId
                LEFT JOIN exchange."DeliveryPoints" as bdp 
                    ON bdp."Id" = bo."DeliveryPointId"
                LEFT JOIN transport."Route" AS tr
                    ON tr."OriginId" = sdp."ClosestTownId" AND
                    tr."DestinationId" = bdp."ClosestTownId"
                LEFT JOIN transport."TruckLoad" as tl 
                    ON tl."AnimalId" = bo."AnimalId" AND
                    tl."AgeId" = @ageId
                LEFT JOIN transport."TruckType" as tt 
                    ON tt."Id" = tl."TruckTypeId"
                LEFT JOIN redmeat."Age" AS a
                    ON a."Id" = @ageId
                LEFT JOIN exchange."ParamsPerCountry" as ppc 
                    ON ppc."CountryId" = 1
                WHERE bo."AnimalId" = @animalId AND
                    bo."AgeId" = @ageId AND
                    Current_Date BETWEEN bo."DateFrom" AND bo."DateTo"
                ) AS t    
                """
        row       = await _pg.fetchrow(qMeatBestPrice, params)
        prices    = dict(row)   #  [dict(row) for row in rows][0]
    else:
        qCropBestPrice = """
            SELECT
                CASE WHEN t."PriceTypeId" <> 1 THEN 'R' || price::text
                    ELSE t.month || ' ' ||
                        CASE WHEN price < 0 THEN '-' ELSE '+' END ||
                        Abs(price)::text END   AS price
            FROM
                (SELECT DISTINCT ON (t."CropId")
                    t."CropId",
                    t."PriceTypeId",
                    t.month,
                    Round(t."Price" -
                        t."FeePerTon" -
                        Greatest(COALESCE(t."HistoryPerTon", "ApproximatePerTon"),
                                "MinTransport")::int)                                AS price
                FROM
                    (SELECT
                        convertPrice(bo."Price", bo."PriceTypeId", bo."ExchangeValue")	AS "Price",			
                        bo."PriceTypeId", bo."CropId",
                        Left(m."Name", 3) AS month,
                        ppc."FeePerTon",
                        COALESCE(ct."PricePerTon",
                                ctc."PricePerTon")                                      AS "HistoryPerTon",
                        Round(tr."Kilos" * ppc."PerTonPerCrowKm")   +
                        Round(ppc."MinTransport")                                        AS "ApproximatePerTon",
                        Round(ppc."MinTransport")                                        AS "MinTransport"		
                    FROM exchange."BulkOrder" as bo 
                    INNER JOIN exchange."DeliveryPoints" as bdp 
                        ON bdp."Id" = bo."DeliveryPointId" 
                    INNER JOIN exchange."DeliveryPoints" as sdp 
                        ON sdp."Id" = @townId
                    INNER JOIN exchange."ParamsPerCountry" as ppc 
                        ON ppc."CountryId" = 1
                    LEFT JOIN exchange."Months" AS m
                        ON m."Id" = bo."MonthId"
                    LEFT JOIN transport."CropTariff" AS ct
                        ON ct."OriginId" = sdp."Id" AND
                        ct."DestinationId" = bdp."Id" AND
                        ct."CropId" = bo."CropId"
                    LEFT JOIN transport."CropTariff" AS ctc
                        ON ctc."OriginId" = sdp."ClosestTownId" AND
                        ctc."DestinationId" = bdp."ClosestTownId" AND
                        ctc."CropId" = bo."CropId"
                    LEFT JOIN transport."Route" AS tr
                        ON tr."OriginId" = sdp."ClosestTownId" AND
                        tr."DestinationId" = bdp."ClosestTownId" 
                    WHERE Current_Date BETWEEN bo."DateFrom" AND bo."DateTo" AND
                        bo."CropId" = @cropId AND bo."OrderType" = 'B' AND
                        bo."CountryId" = 1
                    ) AS t
                ORDER BY "CropId", price DESC
                ) AS t
            """
        val     = await _pg.fetchval(qCropBestPrice, params)
        #print("bestPrice =", val)
        return val

def extractMemory(params, arguments):
    #print("\nextractMemory params =", params, ", arguments =", arguments)
    memories         = []
    for key, val in params.items():
        if key[-2:] == 'Id':
            name     = key[:-2]              # drop Id at the end
        else:
            name     = key
        if name == 'animal': 
            name = 'crop'
        if name != 'user':
            val      = arguments.get(name, None)
            if val:
                memories    += [f'{name} = {val}']
    memory           = 'MEMORY: ' + ', '.join(memories) if memories else None
    return memory    

# ----- parse chatGpt responses and enter info into DB --------------
async def insertMeatPreOffer(params):
    qInsertMeatPreOffer  = """
        INSERT INTO redmeat."MeatPreOrder" ("AnimalId", "AgeId", "OrderType", "Quantity", "DryPrice", 
                                            "CurrencyId", "BulkEntityId", "CreatorId", "DeliveryPointId")
        VALUES 
            (@animalId, @ageId, 'S', @quantity, @price, 1, @entityId, @userId, @townId)
        """
    ret              = await _pg.execute(qInsertMeatPreOffer, params)
    return True

async def insertCropPreOffer(params):
    qInsertCropPreOffer  = """
        INSERT INTO exchange."CropPreOrder"("CropId", "OrderType", "Quantity", "Price", 
                                            "CurrencyId", "BulkEntityId", "CreatorId", "DeliveryPointId")
        VALUES 
            (@cropId, 'S', @quantity, @price, 1, @entityId, @userId, @townId)
        """
    ret              = await _pg.execute(qInsertCropPreOffer, params)
    print("insertCropPreOffer params =", params, ", ret =", ret)
    return True


async def parseAsk(user, tool_obj):
    global step
    db.step              = 100
    # parse tool_obj according to function
    function             = tool_obj.name
    arguments_str        = tool_obj.arguments
    arguments            = json.loads(arguments_str) if arguments_str else {}

    if function == 'crop_price':
        func             = 'crop_price'
        db.step          = 101
        crop_str         = arguments['crop']
        town_str         = arguments['town']
        age_str          = arguments.get('age', "")
        chat_act         = json.dumps({'crop': crop_str, 'town': town_str, 'age': age_str})
        db.step             = 120
        params, retry_str  = await parseCropTownAge(user, crop_str, town_str, age_str)
        db.step             = 121
        memory           = extractMemory(params, arguments)
        if retry_str:
            return {'reply': '', 'retry': retry_str, 'chat': chat_act, 'memory': memory, 'func': None}

        price            = await getBestPrice(crop_str, params)
        if not price:
            reply        = f"I am sorry but we don't have an active bid for your {age_str + ' ' + crop_str} offer in the system. " + \
                            " Despite that, you are welcome to enter an offer into our system. " + \
                            " New bids are entered all the time and your entry will allow buyers to bid on your offer."
        elif crop_str in ('cattle', 'sheep', 'goat'):
            reply            = f"The best bid price for your offer of {age_str + ' ' + crop_str} from {town_str} is R{price}/kg."
        else:
            reply            = f"The best bid price for your offer of {crop_str} from {town_str} is {price}/MT."
        if not user or not user['Id']:
            reply       += """
                If you enroll in our system, you will be able to make preliminary offers directly from your WhatsApp.
                If you want to enroll, please type you name, surname and email address. One of our brokers will then
                contact you to finalize the enrollment. 
                """
        else:
            reply       += '\n\nYou can now place a preliminary sell offer by typing the word "offer" together with the desired price and the quantity on offer.'
        return {'reply': reply, 'chat': chat_act, 'retry': retry_str, 'memory': memory, 'func': None}
    elif function == 'crop_offer':
        db.step          = 150
        #print("arguments =", arguments)

            #return reply, None, None

        crop_str         = arguments['crop']
        age_str          = arguments.get('age', "")
        town_str         = arguments['town']
        price            = arguments['price']
        quantity         = arguments['quantity']
        entity           = arguments.get('entity', "")
        chat_act         = json.dumps({'crop': crop_str, 'town': town_str, 'age': age_str, 'price': price, 'quantity': quantity, 'entity': entity})

        if not user or not user['Id']:
            reply        = "Unfortunately we cannot enter your sell offer into the system because you are not yet enrolled in our system." + \
                           "Please contact Match MX to enroll."
            return {'reply': reply, 'chat': chat_act, 'memory': None, 'retry': None, 'func': None}

        db.step          = 156
        params, retry_str, entity  = await parseCropOffer(user, crop_str, town_str, price, quantity, age_str, entity)
        db.step          = 170
        memory           = extractMemory(params, arguments)
        if retry_str:
            return {'reply': '', 'retry': retry_str, 'chat': chat_act, 'memory': memory, 'func': None}

        db.step          = 151

        if not params.get('entityId', None):
            db.step      = 153
            reply        = "Unfortunately, you are not allowed to create offers for any of the entities that you are linked to."
            return {'reply': reply, 'retry': '', 'chat': chat_act, 'memory': memory, 'func': None}

        if crop_str in ('cattle', 'sheep', 'goat'):
            db.step          = 154
            await insertMeatPreOffer(params)
            reply            = f'''SELL OFFER PLACED:\nA preliminary sell offer for {quantity} {crop_str} of age {age_str} from {town_str} at a price of R{price} was successfully entered into the system for entity {entity}.''' + \
                                '''\n\nOne of our brokers will contact you as soon as possible to finalize your offer.'''
            return {'reply': reply, 'retry': '', 'chat': chat_act, 'memory': memory, 'func': None}
        else:
            db.step          = 155
            await insertCropPreOffer(params)
            reply            = f'''SELL OFFER PLACED:\nA preliminary sell offer for {quantity} metric tons of {crop_str} from {town_str} at a price of R{price} was successfully entered into the system for entity {entity}.''' + \
                                '''\n\nOne of our brokers will contact you as soon as possible to finalize your offer.'''
            return {'reply': reply, 'retry': '', 'chat': chat_act, 'memory': memory, 'func': None}

    else:
        print("======> unknown function", tool_obj)
        reply           = f''' Error: unknown function = {function}, arguments = {str(arguments)}. Please contact MatchMX for assistance'''
        return {'reply': reply, 'chat': None, 'status': 'error', 'func': None}
    


