"""
click_tracking_railway.py - Click Tracking with Bot Detection for Railway
Production-ready version without ngrok dependency
"""

from flask import Flask, redirect, request, jsonify
from flask_cors import CORS
import json
import os
from datetime import datetime
from urllib.parse import urlencode
import hashlib
import re
import time

app = Flask(__name__)
CORS(app)

# Configuration
CLICKS_DB_FILE = "clicks_correct.json"
FINAL_DESTINATION = "https://nonai.life/"
PORT = int(os.getenv("PORT", 5000))  # Railway provides PORT env variable

# Get the public URL from environment (Railway will set this)
# You'll set this in Railway dashboard as RAILWAY_PUBLIC_DOMAIN
PUBLIC_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")

# Bot/Preview user agents to IGNORE
BOT_USER_AGENTS = [
    'facebookexternalhit', 'Twitterbot', 'LinkedInBot', 'WhatsApp',
    'TelegramBot', 'Slackbot', 'Discordbot', 'Googlebot', 'Bingbot',
    'YandexBot', 'DuckDuckBot', 'Applebot', 'Slurp', 'ia_archiver',
    'Mediapartners-Google', 'Bytespider', 'Pinterest', 'Iframely',
    'MetaInspector', 'bot', 'crawler', 'spider', 'scraper', 'checker',
    'monitor', 'headless', 'selenium', 'phantomjs', 'puppeteer',
]

# IPs to track for rate limiting
ip_tracker = {}

def is_bot_request(user_agent, ip=None):
    """Check if request is from a bot/preview service."""
    if not user_agent:
        return True
    
    user_agent = user_agent.lower()
    
    for bot_ua in BOT_USER_AGENTS:
        if bot_ua.lower() in user_agent:
            return True
    
    browser_indicators = ['mozilla', 'chrome', 'safari', 'firefox', 'edge', 'opera', 'webkit', 'gecko', 'msie', 'trident']
    mobile_indicators = ['mobile', 'android', 'iphone', 'ipad', 'ipod']
    
    has_browser = any(indicator in user_agent for indicator in browser_indicators)
    has_mobile = any(indicator in user_agent for indicator in mobile_indicators)
    
    if not has_browser and not has_mobile:
        bot_patterns = [r'python', r'requests', r'urllib', r'curl', r'wget', r'http-client', r'go-http', r'java', r'okhttp']
        for pattern in bot_patterns:
            if re.search(pattern, user_agent):
                return True
    
    return False

def is_rate_limited(ip, tracking_id):
    """Check if this IP is clicking too fast."""
    key = f"{ip}_{tracking_id}"
    current_time = time.time()
    
    if key in ip_tracker:
        last_time, count = ip_tracker[key]
        
        if current_time - last_time > 3600:
            ip_tracker[key] = (current_time, 1)
            return False
        
        time_diff = current_time - last_time
        if time_diff < 60 and count >= 5:
            return True
        
        ip_tracker[key] = (current_time, count + 1)
    else:
        ip_tracker[key] = (current_time, 1)
    
    return False

def clean_ip_tracker():
    """Remove old entries from IP tracker."""
    current_time = time.time()
    old_keys = [key for key, (last_time, _) in ip_tracker.items() if current_time - last_time > 3600]
    for key in old_keys:
        del ip_tracker[key]

def get_public_url():
    """Get the public URL for this Railway deployment."""
    if PUBLIC_URL:
        # Ensure it starts with https://
        url = PUBLIC_URL if PUBLIC_URL.startswith('http') else f"https://{PUBLIC_URL}"
        return url
    
    # Fallback: try to construct from Railway environment variables
    railway_env = os.getenv("RAILWAY_STATIC_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_env:
        return f"https://{railway_env}"
    
    # Local development fallback
    return f"http://localhost:{PORT}"

# Initialize data
click_data = {
    "total_clicks": 0,
    "posts": {},
    "click_history": [],
    "bot_requests_blocked": 0
}

def load_data():
    """Load data from file."""
    global click_data
    if os.path.exists(CLICKS_DB_FILE):
        try:
            with open(CLICKS_DB_FILE, 'r') as f:
                click_data = json.load(f)
        except:
            click_data = {
                "total_clicks": 0,
                "posts": {},
                "click_history": [],
                "bot_requests_blocked": 0
            }

def save_data():
    """Save data to file."""
    with open(CLICKS_DB_FILE, 'w') as f:
        json.dump(click_data, f, indent=2)

@app.route('/')
def index():
    """Root endpoint."""
    return jsonify({
        "service": "NoNAI Click Tracking",
        "status": "running",
        "version": "4.0_railway",
        "public_url": get_public_url(),
        "endpoints": {
            "track": "/track/<tracking_id>",
            "analytics": "/api/analytics",
            "health": "/health",
            "generate_url": "/api/generate-tracking-url (POST)",
            "public_url": "/api/public-url"
        }
    })

@app.route('/track/<tracking_id>')
def track_click(tracking_id):
    """Track clicks with BOT DETECTION."""
    try:
        user_agent = request.headers.get('User-Agent', '')
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        referer = request.headers.get('Referer', '')
        
        clean_ip_tracker()
        
        if is_bot_request(user_agent, ip):
            click_data["bot_requests_blocked"] += 1
            print(f"🤖 BLOCKED Bot/Preview: {tracking_id}")
            return redirect(FINAL_DESTINATION, code=302)
        
        if is_rate_limited(ip, tracking_id):
            print(f"🚫 Rate limited: {tracking_id} from {ip}")
            return redirect(FINAL_DESTINATION, code=302)
        
        platform = request.args.get('p', 'unknown')
        badge_type = request.args.get('b', 'unknown')
        
        if tracking_id not in click_data["posts"]:
            click_data["posts"][tracking_id] = {
                "clicks": 0,
                "platform": platform,
                "badge_type": badge_type,
                "username": "unknown",
                "post_url": "",
                "first_click": None,
                "last_click": None,
                "created_at": datetime.now().isoformat()
            }
        
        click_data["posts"][tracking_id]["clicks"] += 1
        click_data["total_clicks"] += 1
        
        now = datetime.now().isoformat()
        if not click_data["posts"][tracking_id]["first_click"]:
            click_data["posts"][tracking_id]["first_click"] = now
        click_data["posts"][tracking_id]["last_click"] = now
        
        click_record = {
            "tracking_id": tracking_id,
            "timestamp": now,
            "platform": platform,
            "badge_type": badge_type,
            "ip": ip[:15],
            "user_agent": user_agent[:30],
            "is_human": True
        }
        click_data["click_history"].append(click_record)
        
        if len(click_data["click_history"]) > 50:
            click_data["click_history"] = click_data["click_history"][-50:]
        
        save_data()
        
        current_clicks = click_data["posts"][tracking_id]["clicks"]
        print(f"🖱️ REAL HUMAN CLICK #{click_data['total_clicks']}")
        print(f"   Tracking ID: {tracking_id}, Clicks: {current_clicks}")
        
        return redirect(FINAL_DESTINATION, code=302)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return redirect(FINAL_DESTINATION, code=302)

@app.route('/api/generate-tracking-url', methods=['POST'])
def generate_tracking_url():
    """Generate tracking URL using Railway public domain."""
    try:
        data = request.json
        
        platform = data.get('platform', 'facebook')
        badge_type = data.get('badge_type', 'gold')
        username = data.get('username', 'unknown')
        
        tracking_id = hashlib.md5(
            f"{platform}_{badge_type}_{datetime.now().timestamp()}_{os.urandom(4).hex()}".encode()
        ).hexdigest()[:8]
        
        click_data["posts"][tracking_id] = {
            "clicks": 0,
            "platform": platform,
            "badge_type": badge_type,
            "username": username,
            "post_url": "",
            "first_click": None,
            "last_click": None,
            "created_at": datetime.now().isoformat()
        }
        
        save_data()
        
        params = {'p': platform[:3], 'b': badge_type[:1]}
        public_url = get_public_url()
        tracking_url = f"{public_url}/track/{tracking_id}?{urlencode(params)}"
        
        print(f"📝 Generated tracking URL: {tracking_id}")
        print(f"   Public URL: {public_url}")
        
        return jsonify({
            "tracking_id": tracking_id,
            "tracking_url": tracking_url,
            "public_url": public_url,
            "post_info": {
                "platform": platform,
                "badge_type": badge_type,
                "username": username,
                "tracking_id": tracking_id,
                "initial_clicks": 0
            }
        })
        
    except Exception as e:
        print(f"❌ Error generating URL: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/update-post-info', methods=['POST'])
def update_post_info():
    """Update post with actual info."""
    try:
        data = request.json
        tracking_id = data.get('tracking_id')
        
        if not tracking_id or tracking_id not in click_data["posts"]:
            return jsonify({"error": "Invalid tracking ID"}), 404
        
        updates = {}
        if 'post_url' in data:
            click_data["posts"][tracking_id]["post_url"] = data['post_url']
            updates['post_url'] = data['post_url']
        
        if 'username' in data and data['username'] != 'unknown':
            click_data["posts"][tracking_id]["username"] = data['username']
            updates['username'] = data['username']
        
        save_data()
        
        return jsonify({
            "status": "success",
            "tracking_id": tracking_id,
            "current_clicks": click_data["posts"][tracking_id]["clicks"],
            "updates": updates
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Get analytics with bot detection stats."""
    try:
        posts_list = []
        for tracking_id, post_data in click_data["posts"].items():
            posts_list.append({
                "tracking_id": tracking_id,
                "clicks": post_data.get("clicks", 0),
                "platform": post_data.get("platform", "unknown"),
                "badge_type": post_data.get("badge_type", "unknown"),
                "username": post_data.get("username", "unknown"),
                "post_url": post_data.get("post_url", ""),
                "first_click": post_data.get("first_click"),
                "last_click": post_data.get("last_click"),
                "created_at": post_data.get("created_at")
            })
        
        posts_list.sort(key=lambda x: x["clicks"], reverse=True)
        total_clicks = sum(p["clicks"] for p in posts_list)
        
        platform_stats = {}
        badge_stats = {}
        for post in posts_list:
            platform = post["platform"]
            badge = post["badge_type"]
            platform_stats[platform] = platform_stats.get(platform, 0) + post["clicks"]
            badge_stats[badge] = badge_stats.get(badge, 0) + post["clicks"]
        
        recent_human_clicks = [
            {
                "timestamp": click.get("timestamp"),
                "tracking_id": click.get("tracking_id"),
                "platform": click.get("platform", "unknown"),
                "badge_type": click.get("badge_type", "unknown")
            }
            for click in click_data["click_history"][-20:]
            if click.get("is_human", False)
        ]
        
        return jsonify({
            "total_clicks": total_clicks,
            "total_posts": len(posts_list),
            "clicks_by_platform": platform_stats,
            "clicks_by_badge_type": badge_stats,
            "top_posts": posts_list[:20],
            "recent_clicks": recent_human_clicks,
            "avg_clicks_per_post": total_clicks / max(len(posts_list), 1),
            "bot_requests_blocked": click_data.get("bot_requests_blocked", 0),
            "stats": {
                "human_clicks": total_clicks,
                "bot_requests_blocked": click_data.get("bot_requests_blocked", 0),
                "total_requests": total_clicks + click_data.get("bot_requests_blocked", 0)
            }
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/public-url', methods=['GET'])
def get_public_url_endpoint():
    """Get the current public Railway URL."""
    public_url = get_public_url()
    
    return jsonify({
        "public_url": public_url,
        "is_railway": "railway" in public_url.lower() or PUBLIC_URL != "",
        "status": "online",
        "message": "Production URL ready for social media posts",
        "final_destination": FINAL_DESTINATION
    })

@app.route('/api/debug/<tracking_id>', methods=['GET'])
def debug_tracking(tracking_id):
    """Debug specific tracking ID."""
    if tracking_id in click_data["posts"]:
        post_data = click_data["posts"][tracking_id]
        history_clicks = len([
            c for c in click_data["click_history"] 
            if c.get("tracking_id") == tracking_id and c.get("is_human", False)
        ])
        
        return jsonify({
            "tracking_id": tracking_id,
            "post_data": post_data,
            "history_clicks_count": history_clicks,
            "stored_clicks": post_data.get("clicks", 0),
            "matches": history_clicks == post_data.get("clicks", 0)
        })
    
    return jsonify({"error": "Not found"}), 404

@app.route('/api/reset-all', methods=['POST'])
def reset_all():
    """Reset ALL data."""
    global click_data, ip_tracker
    click_data = {
        "total_clicks": 0,
        "posts": {},
        "click_history": [],
        "bot_requests_blocked": 0
    }
    ip_tracker = {}
    save_data()
    return jsonify({
        "status": "success", 
        "message": "All data reset",
        "total_clicks": 0,
        "total_posts": 0
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check for Railway."""
    public_url = get_public_url()
    
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_posts": len(click_data["posts"]),
        "total_clicks": click_data["total_clicks"],
        "bot_requests_blocked": click_data.get("bot_requests_blocked", 0),
        "public_url": public_url,
        "is_production": PUBLIC_URL != "",
        "version": "4.0_railway"
    })

@app.route('/api/test-bot-detection', methods=['GET'])
def test_bot_detection():
    """Test if bot detection is working."""
    user_agent = request.headers.get('User-Agent', '')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    
    is_bot = is_bot_request(user_agent, ip)
    
    return jsonify({
        "user_agent": user_agent,
        "ip": ip,
        "is_bot": is_bot,
        "bot_indicators_found": [
            indicator for indicator in BOT_USER_AGENTS 
            if indicator.lower() in user_agent.lower()
        ]
    })

if __name__ == '__main__':
    print("="*70)
    print("🚂 CLICK TRACKING ON RAILWAY")
    print("="*70)
    print(f"📍 Port: {PORT}")
    print(f"🌐 Public URL: {get_public_url()}")
    print(f"🎯 Redirects to: {FINAL_DESTINATION}")
    
    load_data()
    
    print(f"\n📊 Current Stats:")
    print(f"   Total posts: {len(click_data['posts'])}")
    print(f"   Total clicks: {click_data['total_clicks']}")
    print(f"   Bot requests blocked: {click_data.get('bot_requests_blocked', 0)}")
    print("="*70)
    
    # Railway automatically handles the host binding
    app.run(host='0.0.0.0', port=PORT, debug=False)