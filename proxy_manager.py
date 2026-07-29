def generate_public_url(folder, request_host):
    """Generates the public instance URL based on request host header."""
    if not folder:
        return ""
    # Decide protocol dynamically (HTTPS for production, HTTP for localhost/127.0.0.1)
    protocol = "https" if ("localhost" not in request_host and "127.0.0.1" not in request_host) else "http"
    return f"{protocol}://{request_host}/instance/{folder}"
