import socket
import serial
import threading
import time
import re

GPREDICT_HOST = '0.0.0.0'
GPREDICT_PORT = 4533
SERIAL_PORT = '/dev/ttyUSB0'
SERIAL_BAUDRATE = 115200

class CarryoutRotor:
    def __init__(self, serial_port, baudrate):
        self.ser = serial.Serial(serial_port, baudrate, timeout=1)
        self.lock = threading.Lock()
        self.initialized = False
        self.last_az = 0.0
        self.last_el = 0.0

    def initialize(self):
        if not self.initialized:
            with self.lock:
                self.ser.write(b'\r\n')
                time.sleep(1.0)
                response = b''
                while self.ser.in_waiting:
                    response += self.ser.read(self.ser.in_waiting)
                    time.sleep(0.1)
                response_str = response.decode('ascii', errors='ignore')

            if "MOT>" in response_str:
                print("Already in 'mot' submenu, skipping 'mot' command")
                self.initialized = True
            else:
                response = self.send_command('mot')
                print(f"Sent 'mot' -> Response: {response.strip()}")
                time.sleep(1.0)
                self.initialized = True

    def send_command(self, cmd):
        full_cmd = cmd + '\r\n'
        with self.lock:
            self.ser.write(full_cmd.encode('ascii'))
            time.sleep(1.0)
            response = b''
            while self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
                time.sleep(0.1)
            response_str = response.decode('ascii', errors='ignore')
            print(f"Sent '{cmd}' -> Response:\n{response_str.strip()}")

            if cmd.startswith('a 0'):
                matches = re.findall(r'Angle\[0\]\s*=\s*([-+]?\d*\.\d+|\d+)', response_str)
                if matches:
                    self.last_az = float(matches[0])
                    print(f"Parsed azimuth: {self.last_az}")
                else:
                    print("Warning: Could not parse azimuth angle!")
            elif cmd.startswith('a 1'):
                matches = re.findall(r'Angle\[1\]\s*=\s*([-+]?\d*\.\d+|\d+)', response_str)
                if matches:
                    self.last_el = float(matches[0])
                    print(f"Parsed elevation: {self.last_el}")
                else:
                    print("Warning: Could not parse elevation angle!")

            return response_str

    def move_to(self, az, el):
        self.initialize()
        self.send_command('')  # ENTER
        # Send with 2 decimal places (floats)
        self.send_command(f'a 0 {az:.2f}')
        self.send_command('')  # ENTER
        time.sleep(1.0)
        self.send_command(f'a 1 {el:.2f}')
        self.send_command('')  # ENTER

    def get_position(self):
        self.initialize()
        self.send_command('a 0')  # get azimuth
        self.send_command('a 1')  # get elevation
        return (self.last_az, self.last_el)

def handle_client(conn, addr, rotor):
    print(f"Connection from {addr}")
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            try:
                cmd = data.decode('ascii').strip()
                if cmd.startswith('P'):
                    # Accept decimal degrees from GPredict
                    _, az_str, el_str = cmd.split()
                    az = float(az_str)
                    el = float(el_str)
                    rotor.move_to(az, el)
                    conn.sendall(b'RPRT 0\n')
                elif cmd.startswith('p'):
                    az, el = rotor.get_position()
                    print(f"Sending position to GPredict: az={az:.2f}, el={el:.2f}")
                    response = f"{az:.2f} {el:.2f}\n"
                    conn.sendall(response.encode('ascii'))
                    time.sleep(0.05)
                else:
                    conn.sendall(b'RPRT 0\n')
            except Exception as e:
                print(f"Error: {e}")
                conn.sendall(b'RPRT 1\n')
    finally:
        conn.close()
        print("Gpredict disconnected, exiting.")

def start_server():
    rotor = CarryoutRotor(SERIAL_PORT, SERIAL_BAUDRATE)
    print(f"Carryout antenna connected on {SERIAL_PORT}")
    print(f"Listening for rotor commands on {GPREDICT_HOST} : {GPREDICT_PORT}")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((GPREDICT_HOST, GPREDICT_PORT))
    server.listen(1)

    while True:
        conn, addr = server.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        threading.Thread(target=handle_client, args=(conn, addr, rotor), daemon=True).start()

if __name__ == '__main__':
    start_server()
