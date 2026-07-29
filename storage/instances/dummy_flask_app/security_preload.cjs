try {
    const net = require('net');
    const originalListen = net.Server.prototype.listen;
    net.Server.prototype.listen = function(...args) {
        if (process.env.PORT) {
            const port = parseInt(process.env.PORT);
            if (typeof args[0] === 'number' || (typeof args[0] === 'string' && !isNaN(Number(args[0])))) {
                args[0] = port;
            } else if (args[0] && typeof args[0] === 'object') {
                if ('port' in args[0]) args[0].port = port;
            }
        }
        return originalListen.apply(this, args);
    };
} catch (e) {}
