
from bluepy.btle import UUID, Peripheral, Scanner, DefaultDelegate
import struct

# ====================================
# Utility functions for WavePlus class
# ====================================

def parseSerialNumber(ManuDataHexStr):
    if (ManuDataHexStr is None):
        SN = "Unknown"
    else:
        ManuData = bytearray.fromhex(ManuDataHexStr)

        if (((ManuData[1] << 8) | ManuData[0]) == 0x0334):
            SN  =  ManuData[2]
            SN |= (ManuData[3] << 8)
            SN |= (ManuData[4] << 16)
            SN |= (ManuData[5] << 24)
            SN = str(SN)
            if SN.isdigit() is not True or len(SN) != 10:
                SN = "Unknown"
        else:
            SN = "Unknown"
    return SN



# ===============================
# Class WavePlus
# ===============================

class WavePlus():
    def __init__(self, SerialNumber):
        SerialNumber = str(SerialNumber)
        if SerialNumber.isdigit() is not True or len(SerialNumber) != 10:
            print("Invalid Airthings SerialNumber")
            print("SN is the 10-digit serial number found under the magnetic backplate")
            exit(1)
        self.periph        = None
        self.curr_val_char = None
        self.MacAddr       = None
        self.SN            = SerialNumber
        self.uuid          = UUID("b42e2a68-ade7-11e4-89d3-123b93f75cba")


    def connect(self):
        # Auto-discover device on first connection
        if (self.MacAddr is None):
            scanner     = Scanner().withDelegate(DefaultDelegate())
            searchCount = 0
            while self.MacAddr is None and searchCount < 50:
                devices      = scanner.scan(0.1) # 0.1 seconds scan period
                searchCount += 1
                for dev in devices:
                    ManuData = dev.getValueText(255)
                    SN = parseSerialNumber(ManuData)
                    if (SN == self.SN):
                        self.MacAddr = dev.addr # exits the while loop on next conditional check
                        break # exit for loop

            if (self.MacAddr is None):
                print("ERROR: Could not find device.")
                print("GUIDE: (1) Please verify the serial number.")
                print("       (2) Ensure that the device is advertising.")
                print("       (3) Retry connection.")
                return False

        # Connect to device
        if (self.periph is None):
            self.periph = Peripheral(self.MacAddr)
        if (self.curr_val_char is None):
            self.curr_val_char = self.periph.getCharacteristics(uuid=self.uuid)[0]
        return True


    def read(self):
        if (self.curr_val_char is None):
            print("ERROR: Devices are not connected.")
            return False
        rawdata = self.curr_val_char.read()
        rawdata = struct.unpack('BBBBHHHHHHHH', rawdata)
        sensors = Sensors()
        sensors.set(rawdata)
        return sensors


    def disconnect(self):
        if self.periph is not None:
            self.periph.disconnect()
            self.periph = None
            self.curr_val_char = None
        return True



# ===================================
# Class Sensor and sensor definitions
# ===================================

class Sensors():
    def __init__(self):

        self.sensors = { 'HUMIDITY': "%rH", 'RADON_SHORT_TERM_AVG': "Bq/m3", 'RADON_LONG_TERM_AVG': "Bq/m3", 'TEMPERATURE': "degC", 'REL_ATM_PRESSURE': "hPa", 'CO2_LVL': "ppm", 'VOC_LVL': "ppb" }
        self.sensor_data = {}
        self.sensor_version = None
        for key in self.sensors.keys():
            self.sensor_data[key] = None


    def set(self, rawData):
        self.sensor_version = rawData[0]
        if (self.sensor_version == 1):
            self.sensor_data[list(self.sensors)[0]] = rawData[1]/2.0
            self.sensor_data[list(self.sensors)[1]] = self.conv2radon(rawData[4])
            self.sensor_data[list(self.sensors)[2]] = self.conv2radon(rawData[5])
            self.sensor_data[list(self.sensors)[3]] = rawData[6]/100.0
            self.sensor_data[list(self.sensors)[4]] = rawData[7]/50.0
            self.sensor_data[list(self.sensors)[5]] = rawData[8]*1.0
            self.sensor_data[list(self.sensors)[6]] = rawData[9]*1.0
        else:
            print("ERROR: Unknown sensor version.")
            print("GUIDE: Contact Airthings for support.")
            return False
        return True


    def conv2radon(self, radon_raw):
        radon = "N/A" # Either invalid measurement, or not available
        if 0 <= radon_raw <= 16383:
            radon  = radon_raw
        return radon


    def getNames(self):
        return self.sensors.keys()


    def getValue(self, sensor_name):
        return self.sensor_data[sensor_name]


    def getUnit(self, sensor_name):
        return self.sensors[sensor_name]
