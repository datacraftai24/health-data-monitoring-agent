"""Setup script for Garmin Connect OAuth.

Guides through the OAuth 1.0a flow for Garmin Connect API.

Usage:
    python -m scripts.setup_garmin
"""

import sys


def main():
    print("=" * 60)
    print("Garmin Connect API Setup")
    print("=" * 60)
    print()
    print("1. Register at https://developerportal.garmin.com")
    print("2. Create a new app to get Consumer Key and Consumer Secret")
    print("3. Register webhook endpoints for Push API:")
    print("   - Daily Summary:  POST /webhook/garmin/daily")
    print("   - Activity:       POST /webhook/garmin/activity")
    print()
    print("4. Add to your .env:")
    print("   GARMIN_CONSUMER_KEY=<your-key>")
    print("   GARMIN_CONSUMER_SECRET=<your-secret>")
    print()
    print("5. Complete OAuth flow via Garmin's developer portal")
    print("   to authorize your app to access your Garmin data.")
    print()
    print("Note: Garmin uses a Push API model. Once configured,")
    print("Garmin will POST data to your webhook endpoints")
    print("automatically as new data becomes available.")


if __name__ == "__main__":
    main()
