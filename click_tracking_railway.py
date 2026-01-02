"""
click_tracking_railway.py - FIXED VERSION
Only tracks successful posts & uses correct Railway URL
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
    version="5.1_railway_fixed"
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

# FIXED: Better Railway URL detection
def get_railway_url():
    """Get Railway public URL - FIXED VERSION"""
    # Check Railway environment variables in order of priority
    railway_domain = (
        os.getenv("RAILWAY_PUBLIC_DOMAIN") or 
        os.getenv("RAILWAY_STATIC_URL") or
        os.getenv("RAILWAY_SERVICE_URL")
    )
    
    if railway_domain:
        # Remove any existing protocol
        railway_domain = railway_domain.replace("https://", "").replace("http://", "")
        return f"https://{railway_domain}"
    
    # Fallback for local development only
    return f"http://localhost:{PORT}"

PUBLIC_URL = get_railway_url()

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

class ConfirmPostRequest(BaseModel):
    """NEW: Confirm a post was successful"""
    tracking_id: str
    post_url: str
    platform: str
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
    print("🚂 CLICK TRACKING ON RAILWAY (FIXED VERSION)")
    print("="*70)
    print(f"📍 Port: {PORT}")
    print(f"🌐 Public URL: {PUBLIC_URL}")
    print(f"🎯 Redirects to: {FINAL_DESTINATION}")
    print(f"🔧 Railway Domain: {os.getenv('RAILWAY_PUBLIC_DOMAIN', 'Not set')}")
    
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
        "version": "5.1_railway_fixed",
        "public_url": PUBLIC_URL,
        "endpoints": {
            "track": "/track/{tracking_id}",
            "analytics": "/api/analytics",
            "health": "/health",
            "generate_url": "/api/generate-tracking-url (POST)",
            "confirm_post": "/api/confirm-post (POST)",
            "public_url": "/api/public-url"
        }
    }

@app.get("/track/{tracking_id}")
async def track_click(tracking_id: str, request: Request, p: str = "unknown", b: str = "unknown"):
    """Track clicks with BOT DETECTION - Only for confirmed posts."""
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
        
        # FIXED: Only track if post was confirmed as successful
        if tracking_id not in click_data["posts"]:
            print(f"⚠️ Tracking ID not found or post not confirmed: {tracking_id}")
            return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
        # Check if post is confirmed
        if not click_data["posts"][tracking_id].get("confirmed", False):
            print(f"⚠️ Post not confirmed yet: {tracking_id}")
            return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
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
    """Generate tracking URL - PENDING until confirmed."""
    try:
        tracking_id = hashlib.md5(
            f"{data.platform}_{data.badge_type}_{datetime.now().timestamp()}_{os.urandom(4).hex()}".encode()
        ).hexdigest()[:8]
        
        # Create post but mark as NOT confirmed yet
        click_data["posts"][tracking_id] = {
            "clicks": 0,
            "platform": data.platform,
            "badge_type": data.badge_type,
            "username": data.username,
            "post_url": "",
            "confirmed": False,  # FIXED: Add confirmation flag
            "first_click": None,
            "last_click": None,
            "created_at": datetime.now().isoformat()
        }
        
        save_data()
        
        params = {'p': data.platform[:3], 'b': data.badge_type[:1]}
        tracking_url = f"{PUBLIC_URL}/track/{tracking_id}?{urlencode(params)}"
        
        print(f"📝 Generated tracking URL (pending confirmation): {tracking_id}")
        print(f"   Public URL: {PUBLIC_URL}")
        
        return {
            "tracking_id": tracking_id,
            "tracking_url": tracking_url,
            "public_url": PUBLIC_URL,
            "post_info": {
                "platform": data.platform,
                "badge_type": data.badge_type,
                "username": data.username,
                "tracking_id": tracking_id,
                "initial_clicks": 0,
                "confirmed": False
            }
        }
        
    except Exception as e:
        print(f"❌ Error generating URL: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/confirm-post")
async def confirm_post(data: ConfirmPostRequest):
    """NEW: Confirm a post was successfully published."""
    try:
        if data.tracking_id not in click_data["posts"]:
            raise HTTPException(status_code=404, detail="Tracking ID not found")
        
        # Update post with real URL and mark as confirmed
        click_data["posts"][data.tracking_id].update({
            "post_url": data.post_url,
            "confirmed": True,
            "confirmed_at": datetime.now().isoformat(),
            "platform": data.platform
        })
        
        if data.username and data.username != 'unknown':
            click_data["posts"][data.tracking_id]["username"] = data.username
        
        save_data()
        
        print(f"✅ Post confirmed: {data.tracking_id}")
        print(f"   URL: {data.post_url}")
        print(f"   Platform: {data.platform}")
        
        return {
            "status": "success",
            "tracking_id": data.tracking_id,
            "post_url": data.post_url,
            "confirmed": True,
            "message": "Post confirmed and ready for tracking"
        }
        
    except HTTPException:
        raise
    except Exception as e:
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

"""@app.get("/api/analytics")
async def get_analytics():
    #Get analytics - ONLY confirmed posts.
    try:
        # FIXED: Only include confirmed posts
        posts_list = []
        for tracking_id, post_data in click_data["posts"].items():
            if post_data.get("confirmed", False):  # Only confirmed posts
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
                "badge_type": click.get("badge_type", "unknown"),
                "post_url": click_data["posts"].get(click.get("tracking_id"), {}).get("post_url", ""),
                "username": click_data["posts"].get(click.get("tracking_id"), {}).get("username", "unknown")
            }
            for click in click_data["click_history"][-20:]
            if click.get("is_human", False)
        ]
        
        # Count pending posts
        pending_posts = sum(1 for p in click_data["posts"].values() if not p.get("confirmed", False))
        
        return {
            "total_clicks": total_clicks,
            "total_posts": len(posts_list),
            "pending_posts": pending_posts,
            "clicks_by_platform": platform_stats,
            "clicks_by_badge_type": badge_stats,
            "top_posts": posts_list[:20],
            "recent_clicks": recent_human_clicks,
            "avg_clicks_per_post": total_clicks / max(len(posts_list), 1),
            "bot_requests_blocked": click_data.get("bot_requests_blocked", 0),
            "stats": {
                "human_clicks": total_clicks,
                "bot_requests_blocked": click_data.get("bot_requests_blocked", 0),
                "total_requests": total_clicks + click_data.get("bot_requests_blocked", 0),
                "confirmed_posts": len(posts_list),
                "pending_posts": pending_posts
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))"""

# Add this to your click_tracking_fixed.py or tracking server

# Update the /api/analytics endpoint to include all_posts

@app.get("/api/analytics")
async def get_analytics():
    """
    Get comprehensive analytics including ALL posts (with and without clicks).
    """
    global post_clicks, confirmed_posts
    
    # Calculate stats
    total_clicks = sum(len(clicks) for clicks in post_clicks.values())
    unique_users = len(set(
        click.get('user_id', 'unknown') 
        for clicks in post_clicks.values() 
        for click in clicks
    ))
    
    # Count clicks by platform
    clicks_by_platform = {}
    for tracking_id, clicks in post_clicks.items():
        post = confirmed_posts.get(tracking_id, {})
        platform = post.get('platform', 'unknown')
        clicks_by_platform[platform] = clicks_by_platform.get(platform, 0) + len(clicks)
    
    # Count clicks by badge type
    clicks_by_badge_type = {}
    for tracking_id, clicks in post_clicks.items():
        post = confirmed_posts.get(tracking_id, {})
        badge_type = post.get('badge_type', 'unknown')
        clicks_by_badge_type[badge_type] = clicks_by_badge_type.get(badge_type, 0) + len(clicks)
    
    # Get top posts
    top_posts = []
    for tracking_id, clicks in post_clicks.items():
        post = confirmed_posts.get(tracking_id, {})
        if post:
            click_count = len(clicks)
            first_click = min(click['timestamp'] for click in clicks) if clicks else None
            last_click = max(click['timestamp'] for click in clicks) if clicks else None
            
            top_posts.append({
                'tracking_id': tracking_id,
                'post_url': post.get('post_url', 'N/A'),
                'platform': post.get('platform', 'unknown'),
                'badge_type': post.get('badge_type', 'unknown'),
                'username': post.get('username', 'Unknown'),
                'clicks': click_count,
                'first_click': first_click,
                'last_click': last_click
            })
    
    # Sort by clicks
    top_posts.sort(key=lambda x: x['clicks'], reverse=True)
    
    # Get recent clicks (last 20)
    recent_clicks = []
    for tracking_id, clicks in post_clicks.items():
        post = confirmed_posts.get(tracking_id, {})
        for click in clicks[-20:]:  # Last 20 clicks for this post
            recent_clicks.append({
                'timestamp': click['timestamp'],
                'tracking_id': tracking_id,
                'post_url': post.get('post_url', 'N/A'),
                'platform': post.get('platform', 'unknown'),
                'badge_type': post.get('badge_type', 'unknown'),
                'username': post.get('username', 'Unknown'),
                'user_id': click.get('user_id', 'Unknown')
            })
    
    # Sort by timestamp
    recent_clicks.sort(key=lambda x: x['timestamp'], reverse=True)
    
    # NEW: Get ALL confirmed posts (including those with 0 clicks)
    all_posts = []
    for tracking_id, post in confirmed_posts.items():
        click_count = len(post_clicks.get(tracking_id, []))
        first_click = None
        last_click = None
        
        if click_count > 0:
            clicks = post_clicks.get(tracking_id, [])
            first_click = min(click['timestamp'] for click in clicks)
            last_click = max(click['timestamp'] for click in clicks)
        
        all_posts.append({
            'tracking_id': tracking_id,
            'username': post.get('username', 'Unknown'),
            'post_url': post.get('post_url', 'N/A'),
            'platform': post.get('platform', 'unknown'),
            'badge_type': post.get('badge_type', 'unknown'),
            'clicks': click_count,
            'posted_at': post.get('confirmed_at', 'N/A'),
            'first_click': first_click,
            'last_click': last_click,
            'status': 'active' if click_count > 0 else 'no_clicks'
        })
    
    # Sort all posts by posted_at (most recent first)
    all_posts.sort(key=lambda x: x.get('posted_at', ''), reverse=True)
    
    return {
        'total_clicks': total_clicks,
        'unique_users': unique_users,
        'total_posts': len(confirmed_posts),
        'posts_with_clicks': len(top_posts),
        'posts_without_clicks': len(confirmed_posts) - len(top_posts),
        'avg_clicks_per_post': total_clicks / len(confirmed_posts) if confirmed_posts else 0,
        'clicks_by_platform': clicks_by_platform,
        'clicks_by_badge_type': clicks_by_badge_type,
        'top_posts': top_posts[:50],  # Top 50 posts
        'recent_clicks': recent_clicks[:20],  # Last 20 clicks
        'all_posts': all_posts  # NEW: All posts with full details
    }

@app.get("/api/public-url")
async def get_public_url_endpoint():
    """Get the current public Railway URL."""
    return {
        "public_url": PUBLIC_URL,
        "is_railway": "railway" in PUBLIC_URL.lower(),
        "status": "online",
        "message": "Production URL ready for social media posts",
        "final_destination": FINAL_DESTINATION,
        "environment": {
            "RAILWAY_PUBLIC_DOMAIN": os.getenv("RAILWAY_PUBLIC_DOMAIN", "Not set"),
            "RAILWAY_STATIC_URL": os.getenv("RAILWAY_STATIC_URL", "Not set"),
            "PORT": PORT
        }
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
            "confirmed": post_data.get("confirmed", False),
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
    confirmed_posts = sum(1 for p in click_data["posts"].values() if p.get("confirmed", False))
    pending_posts = len(click_data["posts"]) - confirmed_posts
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "total_posts": confirmed_posts,
        "pending_posts": pending_posts,
        "total_clicks": click_data["total_clicks"],
        "bot_requests_blocked": click_data.get("bot_requests_blocked", 0),
        "public_url": PUBLIC_URL,
        "is_production": "railway" in PUBLIC_URL.lower(),
        "version": "5.1_railway_fixed"
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
