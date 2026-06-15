from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import json
import os
import re
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Frontend से request allow करने के लिए

# Download directory
DOWNLOAD_DIR = '/var/data/downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

@app.route('/')
def home():
    return jsonify({
        'status': '✅ YouTube Downloader API is running',
        'version': '1.0',
        'endpoints': {
            '/info': 'GET - Get video info and formats',
            '/download': 'POST - Download video',
            '/keepalive': 'GET - Keep server alive'
        }
    })

@app.route('/info')
def get_info():
    """Get video information and all available formats"""
    url = request.args.get('url', '')
    
    if not url:
        return jsonify({'error': '❌ Please provide a YouTube URL'}), 400
    
    if 'youtube.com' not in url and 'youtu.be' not in url:
        return jsonify({'error': '❌ Invalid YouTube URL'}), 400
    
    try:
        # yt-dlp से video info लें
        result = subprocess.run(
            ['yt-dlp', '--dump-json', '--no-download', '--no-warnings', 
             '--no-playlist', url],
            capture_output=True, text=True, timeout=30
        )
        
        # अगर fail हो तो दूसरे method से try करें
        if result.returncode != 0:
            result = subprocess.run(
                ['yt-dlp', '--dump-json', '--no-download', '--no-warnings',
                 '--extractor-args', 'youtube:player_client=android', url],
                capture_output=True, text=True, timeout=30
            )
        
        if result.returncode != 0:
            return jsonify({'error': f'❌ Could not fetch video: {result.stderr[:200]}'}), 400
        
        data = json.loads(result.stdout)
        
        # सभी formats process करें
        formats = []
        seen_formats = set()
        
        for fmt in data.get('formats', []):
            if fmt['format_id'] in seen_formats:
                continue
            seen_formats.add(fmt['format_id'])
            
            # Type determine करें
            vcodec = fmt.get('vcodec', 'none')
            acodec = fmt.get('acodec', 'none')
            
            if vcodec == 'none' and acodec != 'none':
                fmt_type = 'audio'
            elif acodec == 'none' and vcodec != 'none':
                fmt_type = 'video'
            else:
                fmt_type = 'full'
            
            # Quality label
            quality = 'N/A'
            if fmt.get('height'):
                quality = f"{fmt['height']}p"
                if fmt.get('fps') and fmt['fps'] > 30:
                    quality += f" {fmt['fps']}fps"
            elif fmt.get('abr'):
                quality = f"{round(fmt['abr'])}kbps"
            
            formats.append({
                'format_id': fmt['format_id'],
                'ext': fmt.get('ext', 'mp4'),
                'height': fmt.get('height'),
                'width': fmt.get('width'),
                'fps': fmt.get('fps'),
                'abr': round(fmt['abr']) if fmt.get('abr') else None,
                'vcodec': vcodec,
                'acodec': acodec,
                'filesize': fmt.get('filesize') or fmt.get('filesize_approx'),
                'quality': quality,
                'type': fmt_type
            })
        
        # Sort formats: best quality first
        formats.sort(key=lambda x: (
            {'full': 0, 'video': 1, 'audio': 2}[x['type']],
            -(x['height'] or 0),
            -(x['abr'] or 0)
        ))
        
        return jsonify({
            'success': True,
            'title': data.get('title', 'Unknown'),
            'channel': data.get('channel') or data.get('uploader', 'Unknown'),
            'duration': data.get('duration', 0),
            'views': data.get('view_count', 0),
            'thumbnail': data.get('thumbnail', ''),
            'formats': formats,
            'format_count': len(formats)
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({'error': '⏱️ Request timeout. Try again.'}), 504
    except Exception as e:
        return jsonify({'error': f'❌ Error: {str(e)}'}), 500

@app.route('/download', methods=['POST'])
def download_video():
    """Download video in selected format"""
    url = request.form.get('url', '')
    format_id = request.form.get('format_id', '')
    
    if not url or not format_id:
        return jsonify({'error': '❌ Missing URL or format_id'}), 400
    
    # Template for output file
    template = os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s')
    
    try:
        result = subprocess.run(
            ['yt-dlp', '-f', format_id, 
             '--merge-output-format', 'mp4',
             '-o', template,
             '--no-warnings',
             '--no-playlist',
             url],
            capture_output=True, text=True, timeout=300
        )
        
        if result.returncode != 0:
            return jsonify({'error': f'❌ Download failed: {result.stderr[:200]}'}), 500
        
        # Find the latest downloaded file
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
        return jsonify({'error': '⏱️ Download timeout. Try smaller file.'}), 504
    except Exception as e:
        return jsonify({'error': f'❌ Error: {str(e)}'}), 500

@app.route('/keepalive')
def keepalive():
    """Keep the server alive"""
    return jsonify({
        'status': 'alive',
        'time': datetime.now().isoformat()
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
