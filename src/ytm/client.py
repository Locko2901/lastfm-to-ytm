from ytmusicapi import YTMusic


def build_oauth_client(auth_path: str) -> YTMusic:
    """Build YTMusic client from auth file."""
    return YTMusic(auth_path)
