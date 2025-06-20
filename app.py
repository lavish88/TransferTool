from flask import Flask, request, jsonify
from subprocess import run, PIPE
import os
import time

app = Flask(__name__)

# FTP server config
FTP_HOST    = "10.10.34.237"
FTP_USER    = "aman"
FTP_PASS    = "ok123"
FTP_DIR     = "recording"

# Paths on the Android device
ADB_DIR     = "/storage/emulated/0/FTP_files"
LOG_PATH    = "/storage/emulated/0/Download/ftp_log.txt"

def run_shell(cmd):
    """Run a shell command; return stdout or None on error."""
    try:
        res = run(cmd, shell=True, check=True, stdout=PIPE, stderr=PIPE)
        return res.stdout.decode().strip()
    except Exception as e:
        print(f"[ERROR] {cmd} => {e}")
        return None

def calculate_throughput(size_bytes, duration_seconds):
    if duration_seconds == 0:
        return 0
    return round((size_bytes * 8) / (duration_seconds * 1000), 2)

def poll_log_for_pattern_indefinitely(device_id, pattern, log_path, poll_interval=2):
    """
    Polls the log file on the device for a pattern, forever (until found).
    Returns the matching line when found.
    """
    while True:
  #      grep_cmd = f'adb -s {device_id} shell "grep -m1 \{pattern} {log_path}"'
  #      grep_cmd = f'adb -s {device_id} shell "grep -m1 \'{pattern}\' {log_path}"'
        grep_cmd = f"adb -s {device_id} shell \"grep -m1 'bytes transferred' {LOG_PATH}\""
        result = run_shell(grep_cmd)
        if result:  # pattern found!
            return result
        time.sleep(poll_interval)


@app.route('/v1/ue_upload_file_to_ftp', methods=['POST'])
def upload_to_android_and_ftp():
    data      = request.get_json() or {}
    file_path = data.get('file_path')
    if not file_path:
        return jsonify(status=400, message='file_path is required'), 400
    if not os.path.exists(file_path):
        return jsonify(status=404, message=f'File not found: {file_path}'), 404

    file_name = os.path.basename(file_path)
    dest_path = f"{ADB_DIR}/{file_name}"

    # 1) detect first connected device
    devs = run_shell("adb devices | grep -w device | awk '{print $1}'")
    if not devs:
        return jsonify(status=500, message='No Android device detected'), 500
    device_id = devs.splitlines()[0]

    # 2) push file to Android
    run_shell(f'adb -s {device_id} shell "mkdir -p {ADB_DIR}"')
    if run_shell(f'adb -s {device_id} push \"{file_path}\" \"{dest_path}\"') is None:
         return jsonify(status=500, message='ADB push failed'), 500
    if run_shell(f'adb -s {device_id} shell ls \"{dest_path}\"') is None:
         return jsonify(status=500, message='File not found on device'), 500

    # 3) clear old log file
    run_shell(f'adb -s {device_id} shell "rm -f {LOG_PATH}"')

    # 4) launch Termux
    run_shell(f'adb -s {device_id} shell am start -n com.termux/.app.TermuxActivity')
    time.sleep(4)
    
    #run_shell(f'adb -s {device_id} shell input text "clear && echo cleared"')
   # time.sleep(4)
   # run_shell(f'adb -s {device_id} shell input keyevent 66')
   # time.sleep(4)
 

    # 5) start logging session
    run_shell(f'adb -s {device_id} shell input text "script\\ -f\\ {LOG_PATH}"')
    run_shell(f'adb -s {device_id} shell input keyevent 66')
    time.sleep(4)


    # 8) upload file & start timer
    start = time.time()
   # run_shell(f'adb -s {device_id} shell input text "put {dest_path}"')
    run_shell(f'adb -s {device_id} shell input text "lftp\ -u\ {FTP_USER},{FTP_PASS}\ {FTP_HOST}"')
    time.sleep(4)
    run_shell(f'adb -s {device_id} shell input keyevent 66')
    time.sleep(4)
    print(f"server's destination directory path : {FTP_DIR}")
    run_shell(f'adb -s {device_id} shell input text "cd\ {FTP_DIR}"')
    time.sleep(4)
    run_shell(f'adb -s {device_id} shell input keyevent 66')
    time.sleep(4)
    run_shell(f'adb -s {device_id} shell input text "put\ {dest_path}"')
    time.sleep(4)

    run_shell(f'adb -s {device_id} shell input keyevent 66')

    
    grep = poll_log_for_pattern_indefinitely(device_id, 'bytes transferred', LOG_PATH, poll_interval=2)
    if not grep:
        return jsonify(status=500, message='FTP did not report successful transfer'), 500
    
    run_shell(f'adb -s {device_id} shell input text "bye"')
    run_shell(f'adb -s {device_id} shell input keyevent 66')

    # 10) end logging session
    run_shell(f'adb -s {device_id} shell input text "exit"')
    run_shell(f'adb -s {device_id} shell input keyevent 66')
    end = time.time()

    # 12) cleanup log
    run_shell(f'adb -s {device_id} shell "rm -f {LOG_PATH}"')

    # 13) compute and return metrics
    size     = os.path.getsize(file_path)
    duration = end - start
    tp       = calculate_throughput(size, duration)

    return jsonify({
        'status': 200,
        'message': f'Successfully uploaded {file_name}',
        'upload_time_sec': round(duration, 3),
        'upload_throughput_kbps': tp,
        'file_size_bytes': size
    }), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
