import os
import sys
import socket

# Low-level socket bind patch to force the assigned port
try:
    if not hasattr(socket.socket, '_original_bind'):
        socket.socket._original_bind = socket.socket.bind
        def patched_bind(self, address, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port and isinstance(address, tuple) and len(address) >= 2:
                host, port = address[0], address[1]
                if isinstance(port, int) and port != 0:
                    address = (host, int(env_port)) + address[2:]
            return socket.socket._original_bind(self, address, *args, **kwargs)
        socket.socket.bind = patched_bind
except Exception:
    pass

# Auto-patch Flask to listen on the assigned port
try:
    import flask
    if not hasattr(flask.Flask, '_original_run'):
        flask.Flask._original_run = flask.Flask.run
        def patched_run(self, host=None, port=None, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port:
                port = int(env_port)
            env_host = os.environ.get("HOST")
            if env_host:
                host = env_host
            return flask.Flask._original_run(self, host=host, port=port, *args, **kwargs)
        flask.Flask.run = patched_run
except Exception:
    pass

# Auto-patch Flask-SocketIO to listen on the assigned port
try:
    import flask_socketio
    if not hasattr(flask_socketio.SocketIO, '_original_run'):
        flask_socketio.SocketIO._original_run = flask_socketio.SocketIO.run
        def patched_socketio_run(self, app, host=None, port=None, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port:
                port = int(env_port)
            env_host = os.environ.get("HOST")
            if env_host:
                host = env_host
            return flask_socketio.SocketIO._original_run(self, app, host=host, port=port, *args, **kwargs)
        flask_socketio.SocketIO.run = patched_socketio_run
except Exception:
    pass

# Auto-patch Uvicorn to listen on the assigned port
try:
    import uvicorn
    if not hasattr(uvicorn, '_original_run'):
        uvicorn._original_run = uvicorn.run
        def patched_uvicorn_run(app, *args, **kwargs):
            env_port = os.environ.get("PORT")
            if env_port:
                kwargs["port"] = int(env_port)
            env_host = os.environ.get("HOST")
            if env_host:
                kwargs["host"] = env_host
            return uvicorn._original_run(app, *args, **kwargs)
        uvicorn.run = patched_uvicorn_run
except Exception:
    pass
