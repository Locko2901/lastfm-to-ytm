from ytmusicapi import YTMusic


def build_oauth_client(auth_path: str) -> YTMusic:
    return YTMusic(auth_path)
