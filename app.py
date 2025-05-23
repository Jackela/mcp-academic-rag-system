#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MCP学术文献RAG服务器主应用入口
"""

import argparse
import logging
import sys
from typing import Optional

# 配置日志
from mcp.server import McpServer # Added import
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='MCP学术文献RAG服务器')
    parser.add_argument('--transport', type=str, default='stdio', 
                        choices=['stdio', 'sse'], 
                        help='MCP传输类型 (stdio或sse)')
    parser.add_argument('--port', type=int, default=3000, 
                        help='HTTP端口号 (仅用于SSE传输)')
    parser.add_argument('--debug', action='store_true', 
                        help='启用调试模式')
    return parser.parse_args()

def init_mcp_server(transport_type: str, port: Optional[int] = None) -> None:
    """
    初始化MCP服务器
    
    注意: 此功能尚未实现，是计划中的功能
    """
    logger.info(f"初始化MCP服务器 (传输类型: {transport_type})")
    
    server = McpServer(name="Academic RAG Server", version="0.1.0") # Instantiated McpServer
    
    if transport_type == 'stdio':
        server.start(transport_type=transport_type) # Called server.start()
    elif transport_type == 'sse':
        server.start(transport_type=transport_type, port=port) # Called server.start() with port
    else:
        logger.error(f"不支持的传输类型: {transport_type}")
        sys.exit(1)

def main() -> None:
    """主函数"""
    args = parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("已启用调试模式")
    
    server_instance = McpServer(name="Academic RAG Server", version="0.1.0")

    try:
        # init_mcp_server(args.transport, args.port) # Old call
        logger.info(f"Initializing MCP server (Transport: {args.transport}, Port: {args.port if args.transport == 'sse' else 'N/A'})")
        
        server_instance.start(transport_type=args.transport, port=args.port if args.transport == 'sse' else None)

        if args.transport == 'sse':
            if server_instance.running and server_instance.http_server_thread:
                logger.info("SSE Server is running. Press Ctrl+C to stop.")
                # Keep the main thread alive while the SSE server (daemon thread) runs.
                while server_instance.running:
                    try:
                        threading.Event().wait(1) # Keep main thread alive, check every second
                    except KeyboardInterrupt:
                        logger.info("Keyboard interrupt received from console.")
                        break # Exit while loop to proceed to stop
            else:
                logger.error("Server failed to start or did not start in SSE mode correctly.")
        # For 'stdio', server_instance.start() is blocking and will run until 'quit' or EOF.
        # No explicit keep-alive needed here for stdio as start() handles its own loop.

    except KeyboardInterrupt: # This handles Ctrl+C for stdio mode if it's not caught by its own loop
        logger.info("KeyboardInterrupt caught in main, ensuring server shutdown.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred: {e}")
    finally:
        logger.info("Initiating server shutdown sequence...")
        if server_instance: # Ensure server_instance was created
            server_instance.stop()
        logger.info("Server shutdown complete.")
        sys.exit(0) # Ensure clean exit

if __name__ == "__main__":
    # Need to import threading here if not already imported for Event
    import threading # Make sure threading is imported for app.py's main logic
    main()
