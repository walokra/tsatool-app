#!/usr/bin/python
# -*- coding: utf-8 -*-

# Utility functions for tsa package

import logging

log = logging.getLogger(__name__)

def eliminate_umlauts(x):
    """
    Converts ä and ö into a and o.
    """
    umlauts = {
        'ä': 'a',
        'Ä': 'A',
        'ö': 'o',
        'Ö': 'O'
    }
    for k in umlauts.keys():
        x = x.replace(k, umlauts[k])

    return x

def with_errpointer(s, pos):
    """
    Print ``s`` + a new line with a pointer at ``pos``th index
    (to show erroneous parts in strings)
    """
    try:
        pos = int(pos)
        s = str(s)
    except ValueError:
        return s
    if pos < 0:
        return s
    return s + '\n' + '~'*pos + '^ HERE'

def to_pg_identifier(x):
    """
    Converts x (string) such that it can be used as a table or column
    identifier in PostgreSQL.

    If there are whitespaces in the middle,
    they are converted into underscores.

    Raises error if x contains fatally invalid parts, e.g.
    leading digit or a non-alphanumeric character.

    .. note:: Pg identifier length maximum is 63 characters.
        To avoid too long final identifiers
        (that might be concatenated from multiple original ones),
        max length of x here
        is 40 characters, which should be enough for site names too.
    """
    assert type(x) is str

    x = x.strip()

    # Original string without leading/trailing whitespaces
    # is retained for error prompting purposes
    old_x = x
    x = x.lower()
    x = eliminate_umlauts(x)
    x = x.replace(' ', '_')

    # Identifiers used in database and thus not allowed as condition identifiers
    DISABLED_IDENTIFIERS = [
        'stations', 'statobs', 'sensors', 'seobs', 'laskennallinen_anturi', 'tiesaa_asema'
        ]
    if x in DISABLED_IDENTIFIERS:
        errtext = f'"{x}" cannot be used as identifier '
        errtext += 'since it is already reserved in database!'
        raise ValueError(errtext)

    if x[0].isdigit():
        errtext = 'String starts with digit:\n'
        errtext += with_errpointer(x, 0)
        raise ValueError(errtext)

    if len(x) > 63:
        errtext = f'"{x}" is too long, maximum is 40 characters:\n'
        errtext += with_errpointer(x, 63-1)
        raise ValueError(errtext)

    for i, c in enumerate(x):
        if not (c.isalnum() or c == '_'):
            errtext = f'"{x}" contains an invalid character:\n'
            errtext += with_errpointer(x, i)
            raise ValueError(errtext)

    return x

def strfdelta(tdelta, fmt):
    """
    Format timedelta object according to ``fmt`` string.
    ``fmt`` should contain formatting string with placeholders
    ``{days}``, ``{hours}``, ``{minutes}`` and ``{seconds}``.
    """
    d = {'days': tdelta.days}
    d['hours'], rem = divmod(tdelta.seconds, 3600)
    d['minutes'], d['seconds'] = divmod(rem, 60)
    return fmt.format(**d)

def strfdelta_to_minutes(tdelta):
    """
    Format timedelta object to minutes.
    """
    d = {'days': tdelta.days}
    d['hours'], rem = divmod(tdelta.seconds, 3600)
    d['minutes'], d['seconds'] = divmod(rem, 60)
    d = d['days'] * 24*60 + d['hours'] * 60 + d['minutes']
    return d

def trunc_str(s, n=80):
    """
    Truncate string ``s`` such that ``n-4`` first characters + `` ...``
    are returned (e.g., for printing). For shorter strings,
    return ``s`` as it is.
    """
    if len(s) <= n-4:
        return s
    return s[:(n-5)] + ' ...'

def list_local_statids():
    """
    List hard-coded station ids for validation
    without fetching them from the database.
    (These are Digitraffic ids as of 8/2019).
    """
    return set([1001,1093,2011,2119,4003,5023,8007,9032,12007,14004,
        1002,1094,2012,2121,4004,5024,8008,9033,12008,14005,
        1003,1095,2013,2122,4005,5025,8009,9034,12009,14007,
        1004,1096,2014,2123,4006,5026,8010,9035,12010,14008,
        1005,1097,2015,2124,4007,5027,8011,10001,12011,14009,
        1006,1098,2016,2125,4008,5028,8012,10002,12012,14010,
        1007,1099,2017,2126,4009,5029,8014,10003,12013,14011,
        1009,1100,2018,2127,4010,5030,8015,10004,12014,14013,
        1010,1101,2019,2128,4011,6001,8016,10005,12015,14014,
        1011,1103,2020,2129,4012,6002,8017,10006,12016,14015,
        1012,1104,2022,2130,4013,6003,8018,10007,12017,14016,
        1013,1105,2023,3001,4015,6004,8019,10008,12019,14017,
        1014,1106,2025,3002,4016,6005,8020,10009,12020,14018,
        1015,1107,2026,3003,4017,6006,8021,10010,12021,14019,
        1016,1108,2027,3004,4020,6007,8023,10011,12022,14020,
        1017,1109,2028,3005,4021,6008,8024,10012,12023,14021,
        1018,1110,2029,3006,4022,6009,8025,10013,12024,14022,
        1019,1111,2030,3007,4023,6010,8029,10014,12025,14023,
        1020,1112,2031,3011,4024,6011,8030,10015,12026,14024,
        1021,1113,2032,3012,4025,6012,8031,10016,12027,14025,
        1022,1114,2033,3014,4027,6013,8032,10017,12028,14026,
        1030,1115,2034,3015,4028,6014,8033,10018,12029,14027,
        1032,1116,2035,3016,4029,6015,8034,10019,12030,14028,
        1034,1118,2036,3022,4030,6016,8035,10020,12031,14029,
        1035,1119,2037,3023,4031,6017,8036,10021,12032,14030,
        1036,1120,2038,3024,4032,6018,8037,10022,12033,14031,
        1037,1121,2039,3026,4034,6019,8038,10023,12034,14032,
        1041,1122,2040,3029,4035,6020,8040,10024,12035,14033,
        1042,1123,2041,3030,4036,6021,8042,10025,12036,14034,
        1043,1124,2042,3031,4037,6022,8044,10026,12038,14036,
        1044,1125,2043,3032,4038,6023,8046,10027,12039,14037,
        1045,1126,2044,3033,4039,6024,8064,10028,12040,14038,
        1046,1127,2045,3034,4040,6025,8065,10029,12041,14039,
        1047,1128,2046,3035,4041,6026,8066,10030,12042,14040,
        1048,1129,2047,3036,4042,6028,8067,10031,12045,14041,
        1049,1130,2048,3037,4043,6029,8068,10032,12046,14042,
        1050,1131,2049,3038,4044,7001,8069,10033,12047,14043,
        1051,1132,2050,3039,4045,7002,8071,10034,12049,14044,
        1052,1133,2052,3040,4046,7003,8072,10035,12050,14045,
        1053,1134,2054,3041,4047,7004,8073,10036,12051,14046,
        1054,1135,2059,3042,4048,7005,8074,10037,12052,14047,
        1055,1137,2060,3043,4049,7006,8075,10038,12053,14048,
        1056,1138,2061,3044,4050,7007,8077,10039,12054,14049,
        1057,1139,2062,3045,4051,7008,8078,10040,12055,14050,
        1058,1140,2063,3047,4052,7009,8079,10041,12056,14051,
        1059,1141,2065,3048,4053,7010,8080,10042,12057,14054,
        1060,1142,2087,3049,4055,7011,9001,10043,12058,14055,
        1061,1143,2088,3050,4056,7012,9002,10044,12059,14056,
        1062,1144,2089,3051,4057,7013,9003,10045,12060,14057,
        1063,1145,2090,3052,4058,7014,9004,10046,12061,14058,
        1064,1146,2091,3053,4059,7015,9005,10047,12062,14059,
        1065,1147,2092,3054,4060,7016,9006,10048,12063,14060,
        1066,1148,2094,3056,4061,7017,9007,10049,12064,14061,
        1067,1149,2095,3057,4062,7018,9008,10050,12065,16001,
        1068,1150,2096,3058,4063,7019,9009,10051,12066,16002,
        1069,1151,2097,3059,4064,7020,9010,10052,12067,16003,
        1070,1152,2098,3062,4065,7021,9011,10053,12068,16004,
        1071,1153,2099,3063,4066,7022,9012,10054,13001,16005,
        1072,1154,2100,3064,4067,7023,9013,10055,13002,16006,
        1073,1155,2101,3065,4068,7024,9014,10056,13003,16007,
        1074,1156,2102,3066,5001,7025,9015,10057,13004,16008,
        1075,1157,2103,3067,5004,7026,9016,10058,13005,16009,
        1076,1158,2104,3069,5005,7027,9017,10059,13006,16010,
        1078,1159,2105,3072,5006,7028,9018,11001,13007,16011,
        1079,1160,2106,3073,5007,7029,9019,11002,13008,16012,
        1080,1161,2107,3074,5008,7030,9020,11003,13009,18005,
        1081,1162,2108,3075,5009,7031,9021,11004,13010,18006,
        1082,1163,2109,3076,5011,7032,9022,11005,13011,18007,
        1083,1164,2110,3077,5012,7033,9023,11006,13012,
        1085,2002,2111,3078,5013,7034,9024,11007,13013,
        1086,2003,2112,3079,5014,7035,9025,11008,13014,
        1087,2004,2113,3080,5015,8001,9026,12001,13015,
        1088,2006,2114,3081,5016,8002,9027,12002,13016,
        1089,2007,2115,3082,5019,8003,9028,12003,13017,
        1090,2008,2116,3083,5020,8004,9029,12004,14001,
        1091,2009,2117,4001,5021,8005,9030,12005,14002,
        1092,2010,2118,4002,5022,8006,9031,12006,14003])

def list_local_sensors():
    """
    List hard-coded sensor name - id pairs as dict for validation
    without fetching them from the database.
    (These are Digitraffic names and ids as of 8/2019).
    """
    return {"ilma": 1,
    "ilma_derivaatta": 2,
    "tie_1": 3,
    "tie_1_derivaatta": 4,
    "tie_2": 5,
    "tie_2_derivaatta": 6,
    "maa_1": 7,
    "maa_2": 8,
    "kastepiste": 9,
    "jaatymispiste_1": 10,
    "jaatymispiste_2": 11,
    "runko_1": 12,
    "keskituuli": 16,
    "maksimituuli": 17,
    "tuulensuunta": 18,
    "ilmanpaine": 19,
    "ilman_kosteus": 21,
    "sade": 22,
    "sade_intensiteetti": 23,
    "sadesumma": 24,
    "sateen_olomuoto_pwdxx": 25,
    "nakyvyys": 26,
    "keli_1": 27,
    "keli_2": 28,
    "varoitus_1": 29,
    "varoitus_2": 30,
    "johtavuus_1": 31,
    "johtavuus_2": 32,
    "pintasignaali_1": 33,
    "pintasignaali_2": 34,
    "jaataajuus_1": 35,
    "jaataajuus_2": 36,
    "aseman_status_1": 37,
    "aseman_status_2": 38,
    "anturivika": 41,
    "sade_tila": 48,
    "kastepiste_ero_tie": 49,
    "kosteuden_maara_1": 50,
    "kosteuden_maara_2": 51,
    "suolan_maara_1": 52,
    "suolan_maara_2": 53,
    "suolan_vakevyys_1": 54,
    "suolan_vakevyys_2": 55,
    "turvallisuuslampo_1": 56,
    "turvallisuuslampo_2": 57,
    "nakyvyys_metria": 58,
    "kastepiste_ero_ilma": 73,
    "pwd_status": 91,
    "pwd_tila": 92,
    "pwd_nak_tila": 93,
    "lumen_syvyys": 94,
    "aurinkoup": 98,
    "valoisaa": 99,
    "vallitseva_saa": 100,
    "kuituvaste_pieni_1": 130,
    "kuituvaste_pieni_2": 131,
    "kuituvaste_suuri_1": 132,
    "kuituvaste_suuri_2": 133,
    "dsc_vastaanottimen_puhtaus": 135,
    "dsc_status": 136,
    "tie3": 172,
    "tienpinnan_tila3": 174,
    "varoitus3": 175,
    "kitka3": 176,
    "veden_maara3": 177,
    "lumen_maara3": 178,
    "jaan_maara3": 179,
    "aseman_status3": 180,
    "kitka3_luku": 181}

def list_db_sensors(pg_conn):
    """
    Return sensor name-id pairs as dict
    as they appear in the database.
    """
    with pg_conn.cursor() as cur:
        cur.execute("SELECT lower(replace(name, '\"', '')) AS name, id FROM sensors;")
        tb = cur.fetchall()
    return {k:v for k, v in tb}
