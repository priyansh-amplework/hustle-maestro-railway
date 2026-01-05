"""
click_tracking_postgres.py - PostgreSQL VERSION
Tracks clicks using PostgreSQL on Render instead of JSON files
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, List
import os
from datetime import datetime
from urllib.parse import urlencode
import hashlib
import re
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

app = FastAPI(
    title="NoNAI Click Tracking",
    description="Click tracking service with PostgreSQL storage",
    version="6.0_postgres"
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
FINAL_DESTINATION = "https://nonai.life/"
PORT = int(os.getenv("PORT", 5000))
DATABASE_URL = os.getenv("DATABASE_URL")  # Render provides this

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable not set!")

# Fix for Render's postgres:// URL (psycopg2 needs postgresql://)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Railway URL detection
def get_railway_url():
    """Get Railway public URL"""
    railway_domain = (
        os.getenv("RAILWAY_PUBLIC_DOMAIN") or 
        os.getenv("RAILWAY_STATIC_URL") or
        os.getenv("RAILWAY_SERVICE_URL")
    )
    
    if railway_domain:
        railway_domain = railway_domain.replace("https://", "").replace("http://", "")
        return f"https://{railway_domain}"
    
    return f"http://localhost:{PORT}"

PUBLIC_URL = get_railway_url()

# Bot user agents to IGNORE
BOT_USER_AGENTS = [
    'facebookexternalhit', 'Twitterbot', 'LinkedInBot', 'WhatsApp',
    'TelegramBot', 'Slackbot', 'Discordbot', 'Googlebot', 'Bingbot',
    'YandexBot', 'DuckDuckBot', 'Applebot', 'Slurp', 'ia_archiver',
    'Mediapartners-Google', 'Bytespider', 'Pinterest', 'Iframely',
    'MetaInspector', 'bot', 'crawler', 'spider', 'scraper', 'checker',
    'monitor', 'headless', 'selenium', 'phantomjs', 'puppeteer',
]

# IPs to track for rate limiting (in-memory, not critical data)
ip_tracker = {}

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
    tracking_id: str
    post_url: str
    platform: str
    username: Optional[str] = None

# Database Connection Pool
@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

# Database Schema Initialization
def init_database():
    """Create tables if they don't exist"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        
        # Posts table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                tracking_id VARCHAR(16) PRIMARY KEY,
                username VARCHAR(255),
                badge_type VARCHAR(50),
                platform VARCHAR(50),
                post_url TEXT,
                clicks INTEGER DEFAULT 0,
                confirmed BOOLEAN DEFAULT FALSE,
                first_click TIMESTAMP,
                last_click TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                confirmed_at TIMESTAMP
            )
        """)
        
        # Click history table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS click_history (
                id SERIAL PRIMARY KEY,
                tracking_id VARCHAR(16),
                timestamp TIMESTAMP DEFAULT NOW(),
                platform VARCHAR(50),
                badge_type VARCHAR(50),
                ip VARCHAR(50),
                user_agent TEXT,
                is_human BOOLEAN DEFAULT TRUE,
                FOREIGN KEY (tracking_id) REFERENCES posts(tracking_id) ON DELETE CASCADE
            )
        """)
        
        # Stats table (for bot blocking, etc.)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY DEFAULT 1,
                bot_requests_blocked INTEGER DEFAULT 0,
                CHECK (id = 1)
            )
        """)
        
        # Insert initial stats row if not exists
        cur.execute("""
            INSERT INTO stats (id, bot_requests_blocked) 
            VALUES (1, 0) 
            ON CONFLICT (id) DO NOTHING
        """)
        
        # Create indexes for better performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_posts_confirmed ON posts(confirmed)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_click_history_tracking_id ON click_history(tracking_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_click_history_timestamp ON click_history(timestamp DESC)
        """)
        
        conn.commit()
        print("✅ Database tables initialized successfully")

# Helper Functions
def is_bot_request(user_agent: str, ip: str = None) -> bool:
    """Check if request is from a bot/preview service"""
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
    """Check if this IP is clicking too fast"""
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
    """Remove old entries from IP tracker"""
    current_time = time.time()
    old_keys = [key for key, (last_time, _) in ip_tracker.items() if current_time - last_time > 3600]
    for key in old_keys:
        del ip_tracker[key]

def increment_bot_counter():
    """Increment bot requests blocked counter"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE stats SET bot_requests_blocked = bot_requests_blocked + 1 WHERE id = 1")

def get_bot_counter():
    """Get bot requests blocked counter"""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT bot_requests_blocked FROM stats WHERE id = 1")
        result = cur.fetchone()
        return result[0] if result else 0

# Startup Event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    print("="*70)
    print("🐘 CLICK TRACKING WITH POSTGRESQL")
    print("="*70)
    print(f"📍 Port: {PORT}")
    print(f"🌐 Public URL: {PUBLIC_URL}")
    print(f"🎯 Redirects to: {FINAL_DESTINATION}")
    print(f"🗄️ Database: PostgreSQL on Render")
    
    try:
        init_database()
        
        # Get stats
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM posts")
            total_posts = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM posts WHERE confirmed = TRUE")
            confirmed_posts = cur.fetchone()[0]
            
            cur.execute("SELECT SUM(clicks) FROM posts WHERE confirmed = TRUE")
            total_clicks = cur.fetchone()[0] or 0
        
        print(f"\n📊 Current Stats:")
        print(f"   Total posts: {total_posts}")
        print(f"   Confirmed posts: {confirmed_posts}")
        print(f"   Total clicks: {total_clicks}")
        print(f"   Bot requests blocked: {get_bot_counter()}")
        print("="*70)
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        raise

# Routes
@app.get("/")
async def index():
    """Root endpoint"""
    return {
        "service": "NoNAI Click Tracking",
        "status": "running",
        "version": "6.0_postgres",
        "database": "PostgreSQL",
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
    """Track clicks with BOT DETECTION - Only for confirmed posts"""
    try:
        user_agent = request.headers.get('user-agent', '')
        ip = request.headers.get('x-forwarded-for', request.client.host)
        
        clean_ip_tracker()
        
        if is_bot_request(user_agent, ip):
            increment_bot_counter()
            print(f"🤖 BLOCKED Bot/Preview: {tracking_id}")
            return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
        if is_rate_limited(ip, tracking_id):
            print(f"🚫 Rate limited: {tracking_id} from {ip}")
            return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Check if post exists and is confirmed
            cur.execute("""
                SELECT clicks, confirmed FROM posts 
                WHERE tracking_id = %s
            """, (tracking_id,))
            post = cur.fetchone()
            
            if not post or not post['confirmed']:
                print(f"⚠️ Post not found or not confirmed: {tracking_id}")
                return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
            
            # Update clicks
            now = datetime.now()
            cur.execute("""
                UPDATE posts 
                SET clicks = clicks + 1,
                    last_click = %s,
                    first_click = COALESCE(first_click, %s)
                WHERE tracking_id = %s
                RETURNING clicks
            """, (now, now, tracking_id))
            
            new_click_count = cur.fetchone()['clicks']
            
            # Insert click history
            cur.execute("""
                INSERT INTO click_history 
                (tracking_id, platform, badge_type, ip, user_agent, is_human)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (tracking_id, p, b, ip[:15] if ip else "unknown", user_agent[:100], True))
            
            conn.commit()
            
            print(f"🖱️ REAL HUMAN CLICK")
            print(f"   Tracking ID: {tracking_id}, Total Clicks: {new_click_count}")
        
        return RedirectResponse(url=FINAL_DESTINATION, status_code=302)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return RedirectResponse(url=FINAL_DESTINATION, status_code=302)

@app.post("/api/generate-tracking-url")
async def generate_tracking_url(data: TrackingURLRequest):
    """Generate tracking URL - PENDING until confirmed"""
    try:
        tracking_id = hashlib.md5(
            f"{data.platform}_{data.badge_type}_{datetime.now().timestamp()}_{os.urandom(4).hex()}".encode()
        ).hexdigest()[:8]
        
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO posts 
                (tracking_id, username, badge_type, platform, confirmed)
                VALUES (%s, %s, %s, %s, %s)
            """, (tracking_id, data.username, data.badge_type, data.platform, False))
            conn.commit()
        
        params = {'p': data.platform[:3], 'b': data.badge_type[:1]}
        tracking_url = f"{PUBLIC_URL}/track/{tracking_id}?{urlencode(params)}"
        
        print(f"📝 Generated tracking URL (pending confirmation): {tracking_id}")
        
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
    """Confirm a post was successfully published"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            cur.execute("""
                UPDATE posts 
                SET post_url = %s,
                    confirmed = TRUE,
                    confirmed_at = %s,
                    platform = %s
                WHERE tracking_id = %s
                RETURNING tracking_id
            """, (data.post_url, datetime.now(), data.platform, data.tracking_id))
            
            result = cur.fetchone()
            
            if not result:
                raise HTTPException(status_code=404, detail="Tracking ID not found")
            
            if data.username and data.username != 'unknown':
                cur.execute("""
                    UPDATE posts SET username = %s WHERE tracking_id = %s
                """, (data.username, data.tracking_id))
            
            conn.commit()
        
        print(f"✅ Post confirmed: {data.tracking_id}")
        print(f"   URL: {data.post_url}")
        
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

@app.get("/api/analytics")
async def get_analytics():
    """Get comprehensive analytics"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get confirmed posts with all details
            cur.execute("""
                SELECT 
                    tracking_id, username, post_url, platform, badge_type,
                    clicks, first_click, last_click, created_at, confirmed_at
                FROM posts 
                WHERE confirmed = TRUE
                ORDER BY clicks DESC
            """)
            posts = cur.fetchall()
            
            # Total stats
            cur.execute("""
                SELECT 
                    COUNT(*) as total_posts,
                    SUM(clicks) as total_clicks
                FROM posts 
                WHERE confirmed = TRUE
            """)
            totals = cur.fetchone()
            
            # Platform stats
            cur.execute("""
                SELECT platform, SUM(clicks) as clicks
                FROM posts 
                WHERE confirmed = TRUE
                GROUP BY platform
            """)
            platform_stats = {row['platform']: row['clicks'] for row in cur.fetchall()}
            
            # Badge stats
            cur.execute("""
                SELECT badge_type, SUM(clicks) as clicks
                FROM posts 
                WHERE confirmed = TRUE
                GROUP BY badge_type
            """)
            badge_stats = {row['badge_type']: row['clicks'] for row in cur.fetchall()}
            
            # Recent clicks
            cur.execute("""
                SELECT 
                    ch.timestamp, ch.tracking_id, ch.platform, ch.badge_type,
                    p.post_url, p.username
                FROM click_history ch
                JOIN posts p ON ch.tracking_id = p.tracking_id
                WHERE ch.is_human = TRUE
                ORDER BY ch.timestamp DESC
                LIMIT 20
            """)
            recent_clicks = cur.fetchall()
            
            # Pending posts count
            cur.execute("SELECT COUNT(*) FROM posts WHERE confirmed = FALSE")
            pending_posts = cur.fetchone()[0]
            
            # Posts with/without clicks
            posts_with_clicks = sum(1 for p in posts if p['clicks'] > 0)
            posts_without_clicks = len(posts) - posts_with_clicks
        
        # Build response
        all_posts = []
        for post in posts:
            all_posts.append({
                'tracking_id': post['tracking_id'],
                'username': post['username'] or 'Unknown',
                'post_url': post['post_url'] or 'N/A',
                'platform': post['platform'] or 'unknown',
                'badge_type': post['badge_type'] or 'unknown',
                'clicks': post['clicks'],
                'posted_at': post['confirmed_at'].isoformat() if post['confirmed_at'] else post['created_at'].isoformat(),
                'first_click': post['first_click'].isoformat() if post['first_click'] else None,
                'last_click': post['last_click'].isoformat() if post['last_click'] else None,
                'status': 'active' if post['clicks'] > 0 else 'no_clicks'
            })
        
        recent_clicks_formatted = []
        for click in recent_clicks:
            recent_clicks_formatted.append({
                'timestamp': click['timestamp'].isoformat(),
                'tracking_id': click['tracking_id'],
                'post_url': click['post_url'] or 'N/A',
                'platform': click['platform'] or 'unknown',
                'badge_type': click['badge_type'] or 'unknown',
                'username': click['username'] or 'Unknown'
            })
        
        return {
            'total_clicks': totals['total_clicks'] or 0,
            'total_posts': totals['total_posts'] or 0,
            'pending_posts': pending_posts,
            'posts_with_clicks': posts_with_clicks,
            'posts_without_clicks': posts_without_clicks,
            'avg_clicks_per_post': (totals['total_clicks'] or 0) / max(totals['total_posts'] or 1, 1),
            'clicks_by_platform': platform_stats,
            'clicks_by_badge_type': badge_stats,
            'top_posts': all_posts[:50],
            'recent_clicks': recent_clicks_formatted,
            'all_posts': all_posts,
            'bot_requests_blocked': get_bot_counter(),
            'stats': {
                'human_clicks': totals['total_clicks'] or 0,
                'bot_requests_blocked': get_bot_counter(),
                'total_requests': (totals['total_clicks'] or 0) + get_bot_counter(),
                'confirmed_posts': totals['total_posts'] or 0,
                'pending_posts': pending_posts
            }
        }
        
    except Exception as e:
        print(f"❌ Analytics error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/public-url")
async def get_public_url_endpoint():
    """Get the current public Railway URL"""
    return {
        "public_url": PUBLIC_URL,
        "is_railway": "railway" in PUBLIC_URL.lower(),
        "status": "online",
        "message": "Production URL ready for social media posts",
        "final_destination": FINAL_DESTINATION
    }

@app.post("/api/reset-all")
async def reset_all():
    """Reset ALL data"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM click_history")
            cur.execute("DELETE FROM posts")
            cur.execute("UPDATE stats SET bot_requests_blocked = 0 WHERE id = 1")
            conn.commit()
        
        global ip_tracker
        ip_tracker = {}
        
        return {
            "status": "success", 
            "message": "All data reset",
            "total_clicks": 0,
            "total_posts": 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    """Health check"""
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            
            cur.execute("SELECT COUNT(*) FROM posts WHERE confirmed = TRUE")
            confirmed_posts = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM posts WHERE confirmed = FALSE")
            pending_posts = cur.fetchone()[0]
            
            cur.execute("SELECT SUM(clicks) FROM posts WHERE confirmed = TRUE")
            total_clicks = cur.fetchone()[0] or 0
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "total_posts": confirmed_posts,
            "pending_posts": pending_posts,
            "total_clicks": total_clicks,
            "bot_requests_blocked": get_bot_counter(),
            "public_url": PUBLIC_URL,
            "database": "PostgreSQL",
            "is_production": "railway" in PUBLIC_URL.lower(),
            "version": "6.0_postgres"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)