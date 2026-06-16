from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import json
import os

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = '/var/data/downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

@app.route('/')
def home():
    return jsonify({'status': '✅ YT Downloader API is running'})

@app.route('/info')
def get_info():
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': '❌ No URL provided'}), 400
    if 'youtube.com' not in url and 'youtu.be' not in url:
        return jsonify({'error': '❌ Invalid YouTube URL'}), 400
    
    try:
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-download', '--no-warnings', '--no-playlist', url],
            capture_output=True, text=True, timeout=30
        )
        
        if result.returncode != 0:
            result = subprocess.run(
                ['yt-dlp', '--dump-json', '--no-download', '--no-warnings',
                 '--extractor-args', 'youtube:player_client=android', url],
                capture_output=True, text=True, timeout=30
            )
        
        if result.returncode != 0:
            return jsonify({'error': f'❌ Failed: {result.stderr[:200]}'}), 400
        
        data = json.loads(result.stdout)
        
        formats = []
        for fmt in data.get('formats', []):
            fmt_type = 'full'
            if fmt.get('vcodec') == 'none' and fmt.get('acodec') != 'none':
                fmt_type = 'audio'
            elif fmt.get('acodec') == 'none' and fmt.get('vcodec') != 'none':
                fmt_type = 'video'
            
            quality = ''
            if fmt.get('height'):
                quality = f"{fmt['height']}p"
                if fmt.get('fps') and fmt['fps'] > 30:
                    quality += f" {fmt['fps']}fps"
            elif fmt.get('abr'):
                quality = f"{round(fmt['abr'])}kbps"
            else:
                quality = 'N/A'
            
            formats.append({
                'format_id': fmt['format_id'],
                'ext': fmt.get('ext', 'mp4'),
                'height': fmt.get('height'),
                'width': fmt.get('width'),
                'fps': fmt.get('fps'),
                'abr': round(fmt['abr']) if fmt.get('abr') else None,
                'vcodec': fmt.get('vcodec', 'none'),
                'acodec': fmt.get('acodec', 'none'),
                'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
                'quality': quality,
                'type': fmt_type
            })
        
        formats.sort(key=lambda x: (
            {'full': 0, 'video': 1, 'audio': 2}[x['type']],
            -(x['height'] or 0),
            -(x['abr'] or 0)
        ))
        
        return jsonify({
            'title': data.get('title', 'Unknown'),
            'channel': data.get('channel') or data.get('uploader', 'Unknown'),
            'duration': data.get('duration', 0),
            'views': data.get('view_count', 0),
            'thumbnail': data.get('thumbnail', ''),
            'formats': formats,
            'format_count': len(formats)
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': '⏱️ Timeout'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download_video():
    url = request.form.get('url', '')
    format_id = request.form.get('format_id', '')
    
    if not url or not format_id:
        return jsonify({'error': '❌ Missing parameters'}), 400
    
    template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')
    
    try:
        # yt-dlp खुद ही merge कर देता है - ffmpeg की जरूरत नहीं
        result = subprocess.run(
            ['yt-dlp', '-f', format_id, 
             '--merge-output-format', 'mp4',
             '-o', template,
             '--no-warnings', '--no-playlist',
             url],
            capture_output=True, text=True, timeout=300
        )
        
        if result.returncode != 0:
            # बिना merge ke try करें
            result = subprocess.run(
                ['yt-dlp', '-f', format_id, 
                 '-o', template,
                 '--no-warnings', '--no-playlist',
                 url],
                capture_output=True, text=True, timeout=300
            )
        
        if result.returncode != 0:
            return jsonify({'error': f'❌ Download failed: {result.stderr[:200]}'}), 500
        
        # Find latest file
        files = sorted(
            [f for f in os.listdir(DOWNLOAD_DIR) 
             if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))],
            key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)),
            reverse=True
        )
        
        if files:
            filepath = os.path.join(DOWNLOAD_DIR, files[0])
            return send_file(
                filepath,
                as_attachment=True,
                download_name=files[0],
                mimetype='application/octet-stream'
            )
        
        return jsonify({'error': '❌ No file generated'}), 500
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': '⏱️ Timeout'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/keepalive')
def keepalive():
    return 'OK'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
