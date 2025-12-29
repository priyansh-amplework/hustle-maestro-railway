"""
click_tracking_railway.py - Click Tracking with Bot Detection for Railway
FastAPI production-ready version
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import json
import os
from datetime import datetime
from urllib.parse import urlencode
import hashlib
import re
import time

app = FastAPI(
    title="NoNAI Click Tracking",
    description="Click tracking service with bot detection",
    version="5.0_railway_fastapi"
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
CLICKS_DB_FILE = "clicks_correct.json"
FINAL_DESTINATION = "https://nonai.life/"
PORT = int(os.getenv("PORT", 5000))
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

# Initialize data
click_data = {
    "total_clicks": 0,
    "posts": {},
    "click_history": [],
    "bot_requests_blocked": 0
}

# Pydantic Models
class TrackingURLRequest(BaseModel):
    platform: str = "facebook"
    badge_type: str = "gold"
    username: str = "unknown"

class UpdatePostRequest(BaseModel):
    tracking_id: str
    post_url: Optional[str] = None
    username: Optional[str] = None

# Helper Functions
def is_bot_request(user_agent: str, ip: str = None) -> bool:
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

def is_rate_limited(ip: str, tracking_id: str) -> bool:
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

def get_public_url() -> str:
    """Get the public URL for this Railway deployment."""
    if PUBLIC_URL:
        url = PUBLIC_URL if PUBLIC_URL.startswith('http') else f"https://{PUBLIC_URL}"
        return url
    
    railway_env = os.getenv("RAILWAY_STATIC_URL") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
    if railway_env:
        return f"https://{railway_env}"
    
    return f"http://localhost:{PORT}"

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

# Startup Event
@app.on_event("startup")
async def startup_event():
    """Load data on startup."""
    print("="*70)
    print("🚂 CLICK TRACKING ON RAILWAY (FastAPI)")
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

# Routes
@app.get("/")
async def index():
    """Root endpoint."""
    return {
        "service": "NoNAI Click Tracking",
        "status": "running",
        "version": "5.0_railway_fastapi",
        "public_url": get_public_url(),
        "endpoints": {
            "track": "/track/{tracking_id}",
            "analytics": "/api/analytics",
            "health": "/health",
            "generate_url": "/api/generate-tracking-url (POST)",
            "public_url": "/api/public-url"
        }
    }

@app.get("/track/{tracking_id}")
async def track_click(tracking_id: str, request: Request, p: str = "unknown", b: str = "unknown"):
    """Track clicks with BOT DETECTION."""
    try:
        user_agent = request.headers.get('user-agent', '')
        ip = request.headers.get('x-forwarded-for', request.client.host)
        
        clean_ip_tracker()
        
        if is_bot_request(user_agent, ip):
            click_data["bot_requests_blocked"] += 1
            print(f"🤖 BLOCKED Bot/Preview: {tracking_id}")
            return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
        if is_rate_limited(ip, tracking_id):
            print(f"🚫 Rate limited: {tracking_id} from {ip}")
            return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
        if tracking_id not in click_data["posts"]:
            click_data["posts"][tracking_id] = {
                "clicks": 0,
                "platform": p,
                "badge_type": b,
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
            "platform": p,
            "badge_type": b,
            "ip": ip[:15] if ip else "unknown",
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
        
        return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return RedirectResponse(url=FINAL_DESTINATION, status_code=302)

@app.post("/api/generate-tracking-url")
async def generate_tracking_url(data: TrackingURLRequest):
    """Generate tracking URL using Railway public domain."""
    try:
        tracking_id = hashlib.md5(
            f"{data.platform}_{data.badge_type}_{datetime.now().timestamp()}_{os.urandom(4).hex()}".encode()
        ).hexdigest()[:8]
        
        click_data["posts"][tracking_id] = {
            "clicks": 0,
            "platform": data.platform,
            "badge_type": data.badge_type,
            "username": data.username,
            "post_url": "",
            "first_click": None,
            "last_click": None,
            "created_at": datetime.now().isoformat()
        }
        
        save_data()
        
        params = {'p': data.platform[:3], 'b': data.badge_type[:1]}
        public_url = get_public_url()
        tracking_url = f"{public_url}/track/{tracking_id}?{urlencode(params)}"
        
        print(f"📝 Generated tracking URL: {tracking_id}")
        print(f"   Public URL: {public_url}")
        
        return {
            "tracking_id": tracking_id,
            "tracking_url": tracking_url,
            "public_url": public_url,
            "post_info": {
                "platform": data.platform,
                "badge_type": data.badge_type,
                "username": data.username,
                "tracking_id": tracking_id,
                "initial_clicks": 0
            }
        }
        
    except Exception as e:
        print(f"❌ Error generating URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/update-post-info")
async def update_post_info(data: UpdatePostRequest):
    """Update post with actual info."""
    try:
        if not data.tracking_id or data.tracking_id not in click_data["posts"]:
            raise HTTPException(status_code=404, detail="Invalid tracking ID")
        
        updates = {}
        if data.post_url:
            click_data["posts"][data.tracking_id]["post_url"] = data.post_url
            updates['post_url'] = data.post_url
        
        if data.username and data.username != 'unknown':
            click_data["posts"][data.tracking_id]["username"] = data.username
            updates['username'] = data.username
        
        save_data()
        
        return {
            "status": "success",
            "tracking_id": data.tracking_id,
            "current_clicks": click_data["posts"][data.tracking_id]["clicks"],
            "updates": updates
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics")
async def get_analytics():
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
        
        return {
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
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/public-url")
async def get_public_url_endpoint():
    """Get the current public Railway URL."""
    public_url = get_public_url()
    
    return {
        "public_url": public_url,
        "is_railway": "railway" in public_url.lower() or PUBLIC_URL != "",
        "status": "online",
        "message": "Production URL ready for social media posts",
        "final_destination": FINAL_DESTINATION
    }

@app.get("/api/debug/{tracking_id}")
async def debug_tracking(tracking_id: str):
    """Debug specific tracking ID."""
    if tracking_id in click_data["posts"]:
        post_data = click_data["posts"][tracking_id]
        history_clicks = len([
            c for c in click_data["click_history"] 
            if c.get("tracking_id") == tracking_id and c.get("is_human", False)
        ])
        
        return {
            "tracking_id": tracking_id,
            "post_data": post_data,
            "history_clicks_count": history_clicks,
            "stored_clicks": post_data.get("clicks", 0),
            "matches": history_clicks == post_data.get("clicks", 0)
        }
    
    raise HTTPException(status_code=404, detail="Not found")

@app.post("/api/reset-all")
async def reset_all():
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
    return {
        "status": "success", 
        "message": "All data reset",
        "total_clicks": 0,
        "total_posts": 0
    }

@app.get("/health")
async def health():
    """Health check for Railway."""
    public_url = get_public_url()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_posts": len(click_data["posts"]),
        "total_clicks": click_data["total_clicks"],
        "bot_requests_blocked": click_data.get("bot_requests_blocked", 0),
        "public_url": public_url,
        "is_production": PUBLIC_URL != "",
        "version": "5.0_railway_fastapi"
    }

@app.get("/api/test-bot-detection")
async def test_bot_detection(request: Request):
    """Test if bot detection is working."""
    user_agent = request.headers.get('user-agent', '')
    ip = request.headers.get('x-forwarded-for', request.client.host)
    
    is_bot = is_bot_request(user_agent, ip)
    
    return {
        "user_agent": user_agent,
        "ip": ip,
        "is_bot": is_bot,
        "bot_indicators_found": [
            indicator for indicator in BOT_USER_AGENTS 
            if indicator.lower() in user_agent.lower()
        ]
    }
