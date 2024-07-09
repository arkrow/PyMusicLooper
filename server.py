from flask import Flask
import subprocess
from pymusiclooper.cli import cli_main

app = Flask(__name__)

@app.route('/')
def hello():

    kwargs = {
        "split_audio": True,
        "path": '/Users/rohit/Desktop/temp/morning1.wav',
        "min_duration_multiplier": None,
        "min_loop_duration": 60,
        "max_loop_duration": 90,
        "approx_loop_position": None,
        "brute_force": False,
        "disable_pruning": False,
        "output_dir": None,
        "recursive": False,
        "flatten": False,
        "format": "WAV",
        'pairs_count': 20
    }
     
    result = cli_main(kwargs=kwargs)
    
    return result

if __name__ == '__main__':
    app.run(host='localhost', port=3000, debug=True)


# python pymusiclooper/__main__.py -i -d split-audio --path ~/Desktop/temp/morning1.wav --min-loop-duration 60 --max-loop-duration 90
