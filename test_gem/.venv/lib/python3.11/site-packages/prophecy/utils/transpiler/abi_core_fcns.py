# Implementations of AbInitio core functions corresponding to the ones in the file ScalaFunctions.scala
# These get used in UDFs generated as part of the transpilation
from pyspark.sql import Row
from datetime import datetime


class ABIUtil:
    @staticmethod
    def string_split(input: str, delim: str):
        return input.split(delim)

    @staticmethod
    def is_valid(input):
        return input is not None

    @staticmethod
    def lookup(name, *arg):
        raise Exception(f"Lookup for ${name} not supported in UDFs")

    @staticmethod
    def string_split_no_empty(input: str, pattern: str):
        import re
        if input is None:
            return None
        else:
            opt1 = input.split(re.escape(pattern))
            opt2 = input.split(pattern)
            finalSplit = opt2 if len(opt1) == 1 and opt1[0] == input else opt1
            res = filter(lambda x: x != "", finalSplit)
            return [x for x in res]

    @staticmethod
    def string_lrtrim(input: str):
        return None if input is None else input.strip()

    @staticmethod
    def ltrim(input: str):
        import re
        return None if input is None else re.sub("\\s+$", input, "")

    @staticmethod
    def rtrim(input: str):
        import re
        return None if input is None else re.sub("^\\s+", input, "")

    @staticmethod
    def concat(*args: str):
        return "".join(args)

    @staticmethod
    def math_log(number):
        import math
        return math.log(number)

    @staticmethod
    def math_pow(number, power):
        import math
        return math.pow(number, power)

    @staticmethod
    def ceiling(number):
        import math
        return math.ceil(number)

    @staticmethod
    def char_string(charCode: int):
        return chr(charCode)

    @staticmethod
    def force_error(input, threshold=""):
        raise Exception(f"{input}")

    @staticmethod
    def print_error(input: str, threshold: str = ""):
        import traceback
        try:
            raise Exception(f"{threshold}: {input}")
        except:
            traceback.print_exc()
        return ""

    @staticmethod
    def unix_timestamp():
        import time
        return int(time.time())

    @staticmethod
    def now(format: str = "yyyy-dd-MM HH:mm:ss"):
        pyformat = _sparkToPyDateFormat(format)
        return datetime.now().strftime(pyformat)

    @staticmethod
    def datediff(start: str, end: str):
        date1 = ABIUtil.getLocalDateTime(start)
        date2 = ABIUtil.getLocalDateTime(end)
        return (date2 - date1).days

    @staticmethod
    def today():
        start_date_str = "01-01-1900"
        end_date = datetime.now().date()
        date_format = "%d-%m-%Y"
        start_date = datetime.strptime(start_date_str, date_format).date()
        days_elapsed = (end_date - start_date).days
        return days_elapsed

    @staticmethod
    def getLocalDateTime(input):
        from datetime import timedelta
        def _parseFormat(format):
            pyformat = _sparkToPyDateFormat(format)
            return datetime.strptime(input, pyformat).replace(hour=0, minute=0)

        if len(input) == len("yyyy-MM-dd HH:mm:ss"):
            try:
                return _parseFormat("yyyy-MM-dd HH:mm:ss")
            except:
                return _parseFormat("yyyy-dd-MM HH:mm:ss")

        elif len(input) == len("yyyyMMdd"):
            return _parseFormat("yyyyMMdd")

        elif len(input) == len("yyyy"):
            return _parseFormat("yyyy")

        elif len(input) == len("yyyy-dd-MM"):
            try:
                return _parseFormat("yyyy-MM-dd")
            except:
                return _parseFormat("yyyy-dd-MM")

        elif input.isnumeric() and int(input) <= ABIUtil.today():
            return datetime.strptime("01-01-1900", "%d-%m-%Y").replace(hour=0, minute=0) + timedelta(days=input)

        raise Exception(f"${input} not supported")

    @staticmethod
    def datetime_add(
            inputDate,
            days=0,
            hours=0,
            minutes=0,
            seconds=0,
            microseconds=0
    ):
        from datetime import timedelta
        d = ABIUtil.getLocalDateTime(inputDate)
        d = d + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds)
        return d.strftime(_sparkToPyDateFormat("yyyyMMddHHmmssSSS"))

    @staticmethod
    def date_month_end(month: int, year=datetime.now().year):
        from calendar import monthrange
        return monthrange(year, month)[1]

    @staticmethod
    def string_join(strvec, delim: str):
        return None if None in strvec else delim.join(strvec)

    @staticmethod
    def string_is_numeric(input: str):
        import re
        pattern = re.compile('^[0-9]+$')
        return None if input is None else 1 if pattern.fullmatch(input) else 0

    @staticmethod
    def string_rindex(inputStr: str, seekStr: str, offset: int = 0):
        if inputStr is None or seekStr is None:
            return None
        else:
            if offset < len(inputStr):
                index = inputStr[0: len(inputStr) - offset].rindex(seekStr)
                return index + 1
            else:
                return 0

    @staticmethod
    def read_file(_filename: str, baseDirectory: str = ""):
        import traceback
        if _filename is None:
            return None
        elif _filename == "":
            return ""
        else:
            try:
                filepath = ABIUtil.searchAndGetFilePathFromBaseDirectory(_filename, baseDirectory)
                try:
                    with open(filepath, 'r') as file:
                        file_contents = file.read()
                    return file_contents
                except:
                    with open(filepath, 'r', encoding='ISO-8859-1') as file:
                        file_contents = file.read()
                    return file_contents
            except:
                traceback.print_exc()
                return _filename

    @staticmethod
    def searchAndGetFilePathFromBaseDirectory(_filename, baseDirectory):
        import os
        if baseDirectory == "":
            filename = _filename
        else:
            try:
                index = _filename.rindex("/")
                filename = _filename[index + 1:]
            except ValueError:
                filename = _filename
        fullfilename = baseDirectory + filename
        if os.path.exists(fullfilename):
            return fullfilename
        else:
            for root, dirs, files in os.walk(baseDirectory):
                if filename in files:
                    return os.path.join(root, filename)
        return ""

    @staticmethod
    def lower(input: str):
        return None if input is None else input.lower()

    @staticmethod
    def upper(input: str):
        return None if input is None else input.upper()

    @staticmethod
    def string(input):
        return None if input is None else str(input)

    @staticmethod
    def re_match_replace(target, pattern, replacement, offset=0):
        import re
        if target is None or pattern is None or replacement is None:
            return None
        else:
            return target[0:offset] + re.sub(pattern, replacement, target[offset:])

    @staticmethod
    def re_index(input: str, pattern: str, offset: int = 0):
        import re
        if input is None or pattern is None:
            return None
        else:
            g = re.search(pattern, input[offset:])
            if g is None:
                return 0
            else:
                return g.start() + offset

    @staticmethod
    def is_blank(input: str):
        return None if input is None else input.strip() == ""

    @staticmethod
    def length(input: str):
        return None if input is None else len(input)

    @staticmethod
    def string_length(input: str):
        return ABIUtil.length(input)

    @staticmethod
    def string_index(input: str, seek: str, offset: int = 0):
        if input is None or seek is None:
            return -1
        else:
            index = input[offset:].index(seek) + 1
            return index if (index == 0) else index + offset

    @staticmethod
    def string_prefix(input: str, length: int):
        return None if input is None else input[0:length]

    @staticmethod
    def first_defined(first, second):
        return second if first is None else first

    @staticmethod
    def starts_with(input: str, prefix: str):
        return False if input is None else input.startswith(prefix)

    @staticmethod
    def re_get_match(input: str, pattern: str):
        import re
        if input is None:
            return None
        else:
            g = re.search(pattern, input)
            if g is None:
                return None
            else:
                return g.group(0)

    @staticmethod
    def string_lpad(input: str, length, paddingChar=""):
        if input is None:
            return None
        else:
            return input.rjust(length, paddingChar)

    @staticmethod
    def string_pad(input: str, length: int, paddingChar: string = ""):
        return input.ljust(length, paddingChar)

    @staticmethod
    def decimal_lpad(input, length: int, char_to_pad_with: str = "0", decimal_point_char: str = "."):
        import re
        matchString = ABIUtil.re_get_match(str(input),
                                           f"""(-?)([0-9]+(${decimal_point_char})[0-9]+|[0-9]+|(0${decimal_point_char})[0-9]+)""")
        if matchString is None:
            return None

        if len(matchString) > length:
            return matchString
        else:
            paddedInput = matchString.rjust(length, char_to_pad_with)
            finalValue = re.sub("-", "", paddedInput)
            return "-" + finalValue if len(finalValue) < length else finalValue

    @staticmethod
    def decimal_strip(input: str, decimal_point_char: str = "."):
        import re
        if input is None:
            return None
        else:
            matchValue = ABIUtil.re_get_match(str(input),
                                              f"""(-?)([0-9]+(${decimal_point_char})[0-9]+|[0-9]+|(0${decimal_point_char})[0-9]+)""")
            if matchValue is None or matchValue == "":
                return 0
            else:
                return re.sub('\\s+', "", matchValue)

    @staticmethod
    def ends_with(input: str, suffix: str):
        return None if input is None else input.endswith(suffix)

    @staticmethod
    def string_replace_first(input: str, seek: str, newStr: str, offset: int = 0):
        import re
        if input is None or seek is None or newStr is None:
            return None
        else:
            return input[0:offset] + re.sub(seek, newStr, input[offset:], 1)

    @staticmethod
    def string_upcase(input: str):
        return None if input is None else input.upper()

    @staticmethod
    def string_replace(input: str, seek: str, newStr: str, offset: int = 0):
        import re
        if input is None or seek is None or newStr is None:
            return None
        else:
            return input[0:offset] + re.sub(seek, newStr, input[offset:])

    @staticmethod
    def string_like(input: str, pattern: str):
        import re
        pat = re.compile(pattern.replace("%", "(.*)").replace("_", "."))
        return pat.fullmatch(input) is not None

    @staticmethod
    def string_filter(inputStr1: str, inputStr2: str):
        if inputStr1 is None or inputStr2 is None:
            return None
        else:
            res = filter(lambda x: x in set(inputStr2), inputStr1)
            return "".join([x for x in res])

    @staticmethod
    def string_filter_out(inputStr1: str, inputStr2: str):
        if inputStr1 is None or inputStr2 is None:
            return None
        else:
            res = filter(lambda x: x not in set(inputStr2), inputStr1)
            return "".join([x for x in res])

    @staticmethod
    def random_string_value(length: int):
        import random
        alphaNumericCharArray = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvxyz"
        l = len(alphaNumericCharArray)
        return "".join([alphaNumericCharArray[random.randint(0, l - 1)] for idx in range(0, length)])

    @staticmethod
    def isnull(input):
        return input is None

    @staticmethod
    def is_not_null(input):
        return not ABIUtil.isnull(input)

    @staticmethod
    def encrypt_aes_simple(input1, input2):
        return []

    @staticmethod
    def aes_encrypt(input1, input2, input3, input4, input5):
        return ""

    @staticmethod
    def aes_decrypt(input1, input2, input3, input4, input5):
        return ""

    @staticmethod
    def string_from_hex(input: str, padOddSize: int = 0):
        if len(input) % 2 == 1 and padOddSize >= 1:
            input = input + "0"
        else:
            input = input
        return bytes.fromhex(input).decode()

    @staticmethod
    def string_to_hex(input: str):
        return input.encode().hex()

    @staticmethod
    def string_compare(input1: str, input2: str):
        if input1 is None or input2 is None:
            return None
        else:
            if input1 == input2:
                return 0
            elif input1 > input2:
                return 1
            else:
                return -1

    @staticmethod
    def writeLongToBytes(input, length, _endian: str, isUnsigned: bool = False):
        return int(input).to_bytes(length, byteorder=_endian, signed=not isUnsigned)

    @staticmethod
    def writeIntegerToBytes(input, length, _endian: str, isUnsigned: bool = False):
        return int(input).to_bytes(length, byteorder=_endian, signed=not isUnsigned)

    @staticmethod
    def readLongToBytes(input, length, _endian: str, isUnsigned: bool = False):
        return int.from_bytes(input, byteorder=_endian, signed=not isUnsigned)

    @staticmethod
    def readIntegerToBytes(input, length, _endian: str, isUnsigned: bool = False):
        return int.from_bytes(input, byteorder=_endian, signed=not isUnsigned)

    # Non-core Util methods
    @staticmethod
    def splitReinterpretAsArgument(input: str, delimiter: str = ""):
        if len(delimiter) == 0:
            charSet = ['|', '\n']
            sortedCharFrequency = sorted([(input.count(delim), delim) for delim in charSet])
            if len(sortedCharFrequency) > 0:
                highestFrequency = sortedCharFrequency[-1]
                splitChar = highestFrequency[1]
            else:
                splitChar = '\n'
            return input.split(splitChar)
        else:
            return input.split(delimiter)

    @staticmethod
    def getIntegerByteArray(input: int, endian="little"):
        val = int(input)
        return val.to_bytes(val.bit_length() + 7 // 8, endian)

    @staticmethod
    def getByteArray(input):
        import pickle
        if isinstance(input, int):
            return ABIUtil.getIntegerByteArray(input)
        elif isinstance(input, str):
            return bytearray(input.encode("windows-1252"))
        elif isinstance(input, Row):
            values = input.asDict().values()
            if all([isinstance(x, int) for x in values]):
                b = [ABIUtil.getIntegerByteArray(x) for x in values]
                result = bytearray()
                for bb in b:
                    result.append(bb)
                return result

        return pickle.dumps(input)

    @staticmethod
    def hash_SHA256(input):
        import hashlib
        return hashlib.sha256(ABIUtil.getByteArray(input)).digest()

    @staticmethod
    def breakByteArrayIntoWindows(input, windowSize: int, offset: int = 0):
        data = input[offset:]
        l = len(data)
        result = []
        for idx in range(l):
            if idx + windowSize <= l:
                result.append(data[idx: idx + windowSize])
            else:
                break
        return result

    @staticmethod
    def convertToBoolean(input):
        try:
            import numbers
            if isinstance(input, bool):
                return input
            elif isinstance(input, numbers.Number):
                return input > 0
            elif isinstance(input, str):
                if input.isnumeric():
                    return float(input) > 0
                elif input.lower() == "false":
                    return False
                else:
                    return bool(input)
            else:
                return bool(input)
        except:
            return None

    @staticmethod
    def convertToBigDecimal(input):
        try:
            if isinstance(input, str) and (str == "null" or str == "None"):
                return None

            return BigDecimal(input)
        except:
            return None

    @staticmethod
    def convertToInt(input):
        try:
            if isinstance(input, str) and (str == "null" or str == "None"):
                return -2 ** 31  # parity with the scala version

            return int(input)
        except:
            return -2 ** 31

    @staticmethod
    def convertToLong(input):
        try:
            if isinstance(input, str) and (str == "null" or str == "None"):
                return -2 ** 63  # parity with the scala version

            return int(input)
        except:
            return -2 ** 63

    @staticmethod
    def convertToByte(input):
        try:
            import numbers
            if isinstance(input, bytes):
                return input
            elif isinstance(input, numbers.Number):
                return int(input) & 0xFF
            elif isinstance(input, str) and (str == "null" or str == "None"):
                return -127

            return int(input) & 0xFF
        except:
            return -127

    @staticmethod
    def convertInputToInteger(input, isBigEndian: bool):
        endian = "big" if isBigEndian else "little"
        return int.from_bytes(input, byteorder=endian)

    @staticmethod
    def convertInputToByteArray(input):
        if isinstance(input, int):
            size = 8 if input > 2 ** 31 - 1 else 4
            return input.to_bytes(size, "big")
        elif isinstance(input, str):
            return bytearray(input.encode())
        elif isinstance(input, list):
            # Array of bytes
            if all([isinstance(x, bytes) for x in input]):
                return input
            elif all([isinstance(x, list) for x in input]):
                fl = _flatten(input)
                # An Array of Arrays of bytes
                if all([isinstance(x, bytes) for x in fl]):
                    return fl

        return ABIUtil.getByteArray(input)

    @staticmethod
    def updateIndexInRow(input, index, value):
        if isinstance(input, list):
            return input[:index] + [value] + index[index + 1:]
        elif isinstance(input, Row):
            rMap = input.asDict()
            result = {}
            for idx, kv in enumerate(rMap.items()):
                if idx == index:
                    result[kv[0]] = value
                else:
                    result[kv[0]] = kv[1]
            return Row(**rMap)

    @staticmethod
    def compareTo(first, second):
        def normalize(v):
            value = v
            if isinstance(v, str):
                try:
                    value = float(v)
                except:
                    try:
                        value = int(v)
                    except:
                        if v == "True":
                            value = True
                        elif v == "False":
                            value = False
            return value

        firstNormalized = normalize(first)
        secondNormalized = normalize(second)

        if firstNormalized is None or secondNormalized is None:
            return None
        elif firstNormalized < secondNormalized:
            return -1
        elif firstNormalized == secondNormalized:
            return 0
        else:
            return 1

    @staticmethod
    def updateFieldInRow(r: Row, field, value):
        rMap = r.asDict()
        rMap[field] = value
        return Row(**rMap)

    @staticmethod
    def assignFields(r1: Row, r2: Row):
        fields = list(r1.asDict().keys())
        fields1 = list(r2.asDict().keys())
        result = r1
        for f in fields:
            if f in fields1 and r2[f] is not None:
                result = ABIUtil.updateFieldInRow(result, f, r2[f])
        return result

    @staticmethod
    def allocate_with_nulls(ddl):
        import re
        res = {}
        ddl_to_process = ddl
        while True:
            (fieldStr, typeStr, rest) = ABIUtil.getFirstSchemaPart(ddl_to_process)
            if typeStr.lower().startswith("struct<"):
                innerDDL = re.sub(r'^STRUCT<', "", typeStr, re.IGNORECASE)
                innerDDL = re.sub(r'>$', "", innerDDL)
                innerRes = ABIUtil.allocate_with_nulls(innerDDL)
                res[fieldStr] = innerRes
            else:
                res[fieldStr] = None
            if not rest:
                break
            ddl_to_process = rest
        return Row(**res)

    @staticmethod
    def getFirstSchemaPart(ddl):
        angBrackCount = 0
        idx = 0
        firstSpaceIdx = -1
        while idx < len(ddl):
            if ddl[idx] == "<":
                angBrackCount = angBrackCount + 1
            elif ddl[idx] == ">":
                angBrackCount = angBrackCount - 1
            elif ddl[idx] == "," and angBrackCount == 0:
                break
            elif ddl[idx] == " " and firstSpaceIdx == -1:
                firstSpaceIdx = idx
            idx = idx + 1
        fieldStr = ddl[: firstSpaceIdx].strip().removesuffix(":").strip()
        typeStr = ddl[firstSpaceIdx: idx].strip().removeprefix(":").strip()
        rest = ddl[idx:]
        if rest and rest[0] == ",":
            rest = rest[1:]
        return (fieldStr, typeStr, rest.strip())

    @staticmethod
    def changeEndianNessOfInteger(input, isBigEndian, toBigEndian):
        e = "big" if isBigEndian else "little"
        return ABIUtil.convertInputToInteger(int(input).to_bytes(4, byteorder=e), toBigEndian)

    @staticmethod
    def serialise(value, outputFile):
        import pickle
        return pickle.dump(value, outputFile)

    @staticmethod
    def convertInputBytesToStructType(input, typeInfo: list, startByte: int = 0):
        if isinstance(input, list) and all([isinstance(x, int) for x in input]):
            return Row(*input)
        else:
            curPointer = 0
            byteArray = ABIUtil.getByteArray(input)[startByte:]
            stringVal = byteArray.decode("windows-1252")
            rowValues = []
            for curType in typeInfo:
                if curType.startswith("decimal") or curType.startswith("string"):
                    stInd = curType.index("(")
                    endInd = curType.index(")")
                    arg = curType[stInd + 1: endInd]
                    if arg.isnumeric():
                        takeUntil = min(int(arg) + curPointer, len(stringVal))
                        rowValues.append(stringVal[curPointer: takeUntil])
                        curPointer = takeUntil
                    else:
                        trimmedArg = arg.strip()
                        pattern = trimmedArg[1: len(trimmedArg) - 1]
                        index = stringVal[curPointer:].index(pattern)
                        rowValues.append(stringVal[curPointer: index + curPointer])
                        curPointer = curPointer + index + len(pattern)
                elif curType == "long":
                    if curPointer >= len(byteArray):
                        rowValues.append(0)
                    else:
                        slicedByteArray = byteArray[curPointer: curPointer + 8]
                        rowValues.append(int.from_bytes(slicedByteArray, "little"))
                        curPointer = curPointer + 8
                elif curType == "byte":
                    if curPointer >= len(byteArray):
                        rowValues.append(0)
                    else:
                        slicedByteArray = byteArray[curPointer: curPointer + 1]
                        rowValues.append(int.from_bytes(slicedByteArray, "little"))
                        curPointer = curPointer + 1

            return Row(*rowValues)

    @staticmethod
    def serializeObjectToString(input):
        return str(input)

    # IMPLEMENT IF NECESSARY
    @staticmethod
    def first_without_error(*args):
        pass

    @staticmethod
    def directory_listing(_path: str, *pattern):
        pass

    @staticmethod
    def record_info(dml_type: str, includes):
        pass

    @staticmethod
    def multifile_information(path: str, baseDirectory: str = ""):
        pass

    @staticmethod
    def file_information(path: str,
                         baseDirectory: str = "",
                         useLocalFileSystem: bool = False):
        pass


# MISC
def BigDecimal(v):
    import decimal
    return decimal.Decimal(v)


def getContentAsStream(content: str):
    return StringAsStream(content)


class StringAsStream:
    _stream = None

    def __init__(self, input):
        import io
        self._stream = io.StringIO(input)

    def read_string(self, len):
        return self._stream.read(int(len))


# Other utility functions
def substring_scala(input: str, start, length):
    if input is None:
        return None
    else:
        return input[max(start - 1, 0): min(max(length, 0) + max(start - 1, 0), len(input))]


def _flatten(input: list):
    return [item for innerlist in input for item in innerlist]


def _sparkToPyDateFormat(format):
    # Order is important !
    return format.replace("a", "%p") \
        .replace("EEE", "%a") \
        .replace("dd", "%d") \
        .replace("DDD", "%j") \
        .replace("MM", "%m") \
        .replace("mm", "%M") \
        .replace("yyyy", "%Y") \
        .replace("yy", "%y") \
        .replace("hh24", "%H") \
        .replace("HH", "%H") \
        .replace("hh", "%H") \
        .replace("SSS", "%f") \
        .replace("ss", "%S") \
        .replace("z", "%Z")
