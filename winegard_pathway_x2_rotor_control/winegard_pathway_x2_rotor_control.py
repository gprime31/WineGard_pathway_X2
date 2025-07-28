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
        self.last_az_scaled = 0  # integer scaled (e.g. 17000)
        self.last_el_scaled = 0

    def initialize(self):
        if not self.initialized:
            with self.lock:
                self.ser.write(b'\r\n')
                time.sleep(1.0)
                response = b''
                while self.ser.in_waiting:
                    response += self.ser.read(self.ser.in_waiting)
                    time.sleep(0.1)
                response_str = response.decode('utf-8', errors='ignore')

            if "MOT>" in response_str:
                print("Already in 'mot' submenu, skipping 'mot' command")
                self.initialized = True
            else:
                self.send_command('mot')
                time.sleep(1.0)
                self.initialized = True

    def send_command(self, cmd):
        full_cmd = cmd + '\r\n'
        with self.lock:
            self.ser.write(full_cmd.encode('utf-8'))
            time.sleep(1.0)
            response = b''
            while self.ser.in_waiting:
                response += self.ser.read(self.ser.in_waiting)
                time.sleep(0.1)
            response_str = response.decode('utf-8', errors='ignore')
            print(f"Sent '{cmd}' -> Response:\n{response_str.strip()}")

            # Parse scaled values from lines like: "m 0  a 17000  np 111714"
            if cmd.startswith('a 0'):
                match = re.search(r'\bm\s+0\s+a\s+(\d+)', response_str)
                if match:
                    self.last_az_scaled = int(match.group(1))
                    print(f"Parsed azimuth scaled value: {self.last_az_scaled}")
                else:
                    print("Warning: Could not parse azimuth from response!")

            elif cmd.startswith('a 1'):
                match = re.search(r'\bm\s+1\s+a\s+(\d+)', response_str)
                if match:
                    self.last_el_scaled = int(match.group(1))
                    print(f"Parsed elevation scaled value: {self.last_el_scaled}")
                else:
                    print("Warning: Could not parse elevation from response!")

            return response_str

    def move_to(self, az, el):
        self.initialize()
        self.send_command('')  # ENTER to prompt
        self.send_command(f'a 0 {az:.2f}')
        self.send_command('')  # ENTER
        time.sleep(1.0)
        self.send_command(f'a 1 {el:.2f}')
        self.send_command('')  # ENTER

    def get_position(self):
        self.initialize()
        # Just return the last parsed scaled values
        return (self.last_az_scaled, self.last_el_scaled)


def handle_client(conn, addr, rotor):
    print(f"Connection from {addr}")
    try:
        while True:
            data = conn.recv(1024)
            if not data:
                break
            try:
                cmd = data.decode('utf-8').strip()
                if cmd.startswith('P'):
                    _, az_str, el_str = cmd.split()
                    az = float(az_str)
                    el = float(el_str)
                    rotor.move_to(az, el)
                    conn.sendall(b'RPRT 0\n')

                elif cmd.startswith('p'):
                    az_scaled, el_scaled = rotor.get_position()
                    az_deg = az_scaled / 100.0
                    el_deg = el_scaled / 100.0
                    response = f"{az_deg:.2f}\n{el_deg:.2f}\n"
                    print(f"Sending position to Gpredict: {response.strip()}")
                    conn.sendall(response.encode('utf-8'))
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
    print(f"Listening for rotor commands on {GPREDICT_HOST}:{GPREDICT_PORT}")

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
