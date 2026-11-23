"""
Keep passwords and API keys out of plain-text files: they live in Windows Credential Manager (via keyring).

    secure_store.get("llm_api_key")          -> the secret, or "" when not stored
    secure_store.set("llm_api_key", value)   -> store it
Names used: llm_api_key, linkedin_username, linkedin_password.
Run `python migrate_secrets.py` once to move what is currently in user_config.json into the vault.
"""
SERVICE = "linkedin-auto-applier"


def get(name):
    try:
        import keyring
        return keyring.get_password(SERVICE, name) or ""
    except Exception:
        return ""


def set(name, value):
    import keyring
    keyring.set_password(SERVICE, name, value)


def delete(name):
    try:
        import keyring
        keyring.delete_password(SERVICE, name)
    except Exception:
        pass
