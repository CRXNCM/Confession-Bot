import asyncio
from aiohttp import web
import logging

# Set up logging
logger = logging.getLogger(__name__)

class KeepAliveServer:
    def __init__(self, host='0.0.0.0', port=8080):
        self.host = host
        self.port = port
        self.app = web.Application()
        self.app.router.add_get('/', self.handle_request)
        self.runner = None
        self.site = None
        
    async def handle_request(self, request):
        """Handle incoming HTTP requests with a simple response."""
        return web.Response(text="Bot is alive!")
    
    async def start(self):
        """Start the keep-alive server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            self.site = web.TCPSite(self.runner, self.host, self.port)
            await self.site.start()
            logger.info(f"Keep-alive server started on http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start keep-alive server: {e}")
            raise
    
    async def stop(self):
        """Stop the keep-alive server."""
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.cleanup()
        logger.info("Keep-alive server stopped")
    
    async def cleanup(self):
        """Clean up resources."""
        if self.runner:
            await self.runner.cleanup()

# For testing
if __name__ == "__main__":
    import asyncio
    
    async def main():
        server = KeepAliveServer()
        try:
            await server.start()
            # Keep the server running
            while True:
                await asyncio.sleep(3600)  # Sleep for an hour
        except (KeyboardInterrupt, SystemExit):
            await server.stop()
    
    asyncio.run(main())
