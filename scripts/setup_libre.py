"""Setup script for LibreLinkUp authentication.

Run this once to authenticate and get the patient ID for your LibreLinkUp account.
Store the resulting token and patient_id in your .env or user profile.

Usage:
    python -m scripts.setup_libre
"""

import asyncio
import sys

from src.ingestion.libre import LibreLinkUpClient


async def main():
    email = input("LibreLinkUp email: ").strip()
    password = input("LibreLinkUp password: ").strip()

    client = LibreLinkUpClient()

    print("\nAuthenticating...")
    try:
        token = await client.authenticate(email, password)
        print(f"Auth token: {token[:20]}...")
    except Exception as e:
        print(f"Authentication failed: {e}")
        sys.exit(1)

    print("\nFetching connections...")
    connections = await client.get_connections(token)

    if not connections:
        print("No patients found. Make sure someone has shared their data with this account.")
        sys.exit(1)

    print(f"\nFound {len(connections)} connection(s):")
    for i, conn in enumerate(connections):
        name = f"{conn.get('firstName', '')} {conn.get('lastName', '')}".strip()
        patient_id = conn.get("patientId", "unknown")
        glucose = conn.get("glucoseMeasurement", {})
        current = glucose.get("Value", "?")
        print(f"  [{i}] {name} (ID: {patient_id}) — Current glucose: {current} mmol/L")

    print("\nAdd these to your .env file:")
    print(f"  LIBRE_EMAIL={email}")
    print(f"  LIBRE_PASSWORD=<your-password>")
    if connections:
        print(f"  LIBRE_PATIENT_ID={connections[0].get('patientId', '')}")


if __name__ == "__main__":
    asyncio.run(main())
