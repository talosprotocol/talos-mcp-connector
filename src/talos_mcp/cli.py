import json
import os
import sys
import click
from rich.console import Console
from rich.table import Table
from typing import Optional

from talos_mcp.config import TalosMcpConfig, McpResourceConfig
from talos_mcp.transport import create_transport
from talos_mcp.cache import SchemaCache

console = Console()

def get_config(config_path: Optional[str]) -> TalosMcpConfig:
    paths = []
    if config_path:
        paths.append(config_path)
    if os.getenv("TALOS_MCP_CONFIG"):
        paths.append(os.getenv("TALOS_MCP_CONFIG"))
    paths.append("mcp_servers.json")
    paths.append(os.path.expanduser("~/.config/talos/mcp_servers.json"))
    
    for p in paths:
        if os.path.exists(p):
            try:
                return TalosMcpConfig.load(p)
            except Exception as e:
                console.print(f"[red]Error loading config {p}: {e}[/red]")
                sys.exit(1)
                
    console.print("[red]No config file found. Please create mcp_servers.json[/red]")
    sys.exit(1)

# --- Root CLI ---
@click.group()
def cli():
    """Talos CLI"""
    pass

# --- MCP Group ---
@cli.group()
@click.option('--config', help='Path to config file')
@click.pass_context
def mcp(ctx, config):
    """MCP Connector commands"""
    ctx.ensure_object(dict)
    cfg = get_config(config)
    ctx.obj['config'] = cfg
    
    # Access loader if attached per refactor
    loader = getattr(cfg, "_loader", None)
    digest = loader.validate()[:8] if loader else "unknown"
    contracts_ver = "1.2.0" # Pinned
    
    console.print(f"[dim]Startup Config | Contracts: {contracts_ver} | Digest: {digest}[/dim]")
    ctx.obj['cache'] = SchemaCache()

@mcp.command()
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format')
@click.option('--filter', help='Glob filter for server names')
@click.pass_context
def ls(ctx, json_output, filter):
    """List available MCP servers"""
    config: TalosMcpConfig = ctx.obj['config']
    servers = []
    
    import fnmatch
    
    for s_id, s_conf in config.mcpServers.items():
        if filter and not fnmatch.fnmatch(s_id, filter):
            continue
        servers.append({
            "id": s_id,
            "name": s_conf.name,
            "transport": s_conf.transport,
            "metadata": s_conf.metadata
        })
        
    if json_output:
        import json
        print(json.dumps({"servers": servers}, indent=2))
    else:
        table = Table(title="MCP Servers")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Transport", style="green")
        table.add_column("Endpoint/Command")
        
        for s in servers:
            s_conf = config.mcpServers[s['id']]
            endpoint = s_conf.endpoint or s_conf.command
            table.add_row(s['id'], s['name'], s['transport'], str(endpoint))
            
        console.print(table)

@mcp.command()
@click.argument('server_id')
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format')
@click.pass_context
def tools(ctx, server_id, json_output):
    """List tools for a server"""
    config: TalosMcpConfig = ctx.obj['config']
    if server_id not in config.mcpServers:
        console.print(f"[red]Server '{server_id}' not found[/red]")
        sys.exit(1)
        
    server_conf = config.mcpServers[server_id]
    
    try:
        transport = create_transport(server_conf)
        tools = transport.list_tools()
        transport.close()
        
        if json_output:
            print(json.dumps({"server_id": server_id, "tools": tools}, indent=2))
        else:
            table = Table(title=f"Tools for {server_id}")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            
            for t in tools:
                desc = t.get("description", "")
                table.add_row(t["name"], desc.split("\n")[0])
                
            console.print(table)
            
    except Exception as e:
        console.print(f"[red]Error listing tools: {e}[/red]")
        sys.exit(1)

@mcp.command()
@click.argument('server_id')
@click.argument('tool_name')
@click.pass_context
def schema(ctx, server_id, tool_name):
    """Get JSON schema for a tool"""
    config: TalosMcpConfig = ctx.obj['config']
    cache: SchemaCache = ctx.obj['cache']
    
    if server_id not in config.mcpServers:
        console.print(f"[red]Server '{server_id}' not found[/red]")
        sys.exit(1)
        
    # Check cache
    cached_schema = cache.get(server_id, tool_name)
    if cached_schema:
        print(json.dumps(cached_schema, indent=2))
        return

    # Fetch
    server_conf = config.mcpServers[server_id]
    try:
        transport = create_transport(server_conf)
        schema = transport.get_tool_schema(tool_name)
        transport.close()
        
        # Cache it
        cache.put(server_id, tool_name, schema)
        
        print(json.dumps(schema, indent=2))
            
    except Exception as e:
        console.print(f"[red]Error fetching schema: {e}[/red]")
        sys.exit(1)

@mcp.command()
@click.argument('server_id')
@click.argument('tool_name')
@click.option('--input', 'input_json', help='Input arguments as JSON string')
@click.option('--json', 'json_output', is_flag=True, help='Output in JSON format')
@click.pass_context
def call(ctx, server_id, tool_name, input_json, json_output):
    """Call a tool"""
    config: TalosMcpConfig = ctx.obj['config']
    
    if server_id not in config.mcpServers:
        console.print(f"[red]Server '{server_id}' not found[/red]")
        sys.exit(1)
        
    try:
        args = json.loads(input_json) if input_json else {}
    except json.JSONDecodeError:
        console.print("[red]Invalid JSON input[/red]")
        sys.exit(1)

    server_conf = config.mcpServers[server_id]
    try:
        transport = create_transport(server_conf)
        result = transport.call_tool(tool_name, args)
        transport.close()
        
        print(json.dumps(result, indent=2))
            
    except Exception as e:
        console.print(f"[red]Error calling tool: {e}[/red]")
        sys.exit(1)

if __name__ == '__main__':
    cli()
