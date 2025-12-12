from pymongo.mongo_client import MongoClient
import ssl

mongo_client = None
db = None

if MONGO_URL:
    try:
        # Create a TLSv1.2 SSL context
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

        mongo_client = MongoClient(
            MONGO_URL,
            tls=True,
            tlsAllowInvalidCertificates=True,
            tlsCAFile=None,  # ensure Atlas CA not required
            socketTimeoutMS=20000,
            connectTimeoutMS=20000,
            serverSelectionTimeoutMS=8000,
            ssl_context=ssl_ctx  # <-- this is the correct PyMongo 4.x parameter
        )

        mongo_client.admin.command("ping")
        print("✅ MongoDB CONNECTED (TLSv1.2 forced)")

        db = mongo_client["trip_concierge"]

    except Exception as e:
        print(f"❌ MongoDB unreachable — running without DB: {e}")
        db = None
else:
    print("⚠️ MONGO_URL missing — DB disabled")
