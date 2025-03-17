import discord
from discord.ext import commands
import requests
import json
import os
import re
import ipaddress
import asyncio
from datetime import datetime, timezone
import random
import string

# Hardcoded credentials (too lazy to make it a environment variable_
TOKEN = "DiscordBotToken"
CLOUDFLARE_API_KEY = "CloudflareAPIKey"
CLOUDFLARE_EMAIL = "MailOfOwnerAPIKey"
ZONE_ID = "ZoneIDOfBaseDomain"
BASE_DOMAIN = "BaseDomain"

#bot setup
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.guilds = True
intents.members = True
intents.dm_messages = True

bot = commands.Bot(command_prefix="%", intents=intents)

DATA_FILE = "users.json"

# Allowed records
RECORD_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "SRV"]

#Other bot things
SUCCESS_COLOR = 0x4CAF50  # Green
ERROR_COLOR = 0xF44336    # Red
INFO_COLOR = 0x2196F3     # Blue
WARNING_COLOR = 0xFF9800  # Orange

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Error loading data file, creating new one")
            return {}
    else:
        print(f"Data file {DATA_FILE} not found, creating new one")
        return {}

def save_data(data):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
        print("Data saved successfully")
    except Exception as e:
        print(f"Error saving data: {str(e)}")

headers = {
    "X-Auth-Email": CLOUDFLARE_EMAIL,
    "X-Auth-Key": CLOUDFLARE_API_KEY,
    "Content-Type": "application/json"
}

def is_valid_subdomain(name):
    """Check if subdomain name is valid (alphanumeric and hyphen only)"""
    return bool(re.match(r'^[a-zA-Z0-9-]+$', name))

def is_valid_ip(ip):
    """Check if IP address is valid"""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def is_valid_hostname(hostname):
    """Check if hostname is valid"""
    return bool(re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$', hostname))

active_sessions = {}

@bot.event
async def on_ready():
    # Initialize global users dictionary
    global users
    users = load_data()
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    print(f'Connected to {len(bot.guilds)} guilds')
    activity = discord.Activity(type=discord.ActivityType.watching, name="DNS records")
    await bot.change_presence(activity=activity)
    print('------')

@bot.command(name="ping")
async def ping(ctx):
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: {round(bot.latency * 1000)}ms",
        color=INFO_COLOR,
        timestamp=datetime.now(timezone.utc)
    )
    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

def is_admin(ctx):
    return ctx.author.guild_permissions.administrator

@bot.command()
async def commands(ctx):
    embed = discord.Embed(
        title="📋 Bot Commands",
        description="Here's what you can do with this bot:",
        color=INFO_COLOR,
        timestamp=datetime.now(timezone.utc)
    )

    embed.add_field(name="General", value="`%ping` - Check if the bot is responding\n`%balance` - Check your credit balance", inline=False)

    embed.add_field(name="Domain Management", value="`%create_subdomain name` - Create a subdomain (costs 10 credits)\n`%list_subdomains` - List all your subdomains\n`%records` - Interactive DNS record management", inline=False)

    embed.add_field(name="Admin Commands", value="`%add_credits @user amount` - Add credits to a user\n`%remove_subdomain name @user` - Remove a user's subdomain\n`%remove_credits @user amount` - Remove credits from a user\n`%reset_all` - Reset all user data (requires confirmation string)", inline=False)

    embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def balance(ctx):
    try:
        user_id = str(ctx.author.id)
        if user_id not in users:
            users[user_id] = {"credits": 0, "subdomains": []}
            save_data(users)

        credits = users[user_id]["credits"]
        embed = discord.Embed(
            title="💰 Account Balance",
            description=f"You currently have **{credits} credits**.",
            color=INFO_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in balance command: {str(e)}")
        await ctx.send(embed=discord.Embed(title="❌ Error", description="An error occurred while checking your balance.", color=ERROR_COLOR))

@bot.command()
async def add_credits(ctx, member: discord.Member, amount: int):
    try:
        if not is_admin(ctx):
            embed = discord.Embed(title="❌ Permission Denied", description="You don't have permission to use this command.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        user_id = str(member.id)
        if user_id not in users:
            users[user_id] = {"credits": 0, "subdomains": []}

        users[user_id]["credits"] += amount
        save_data(users)

        embed = discord.Embed(
            title="💰 Credits Added",
            description=f"Added **{amount} credits** to {member.mention}.\nThey now have **{users[user_id]['credits']} credits**.",
            color=SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Action by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in add_credits command: {str(e)}")
        await ctx.send(embed=discord.Embed(title="❌ Error", description="An error occurred while adding credits.", color=ERROR_COLOR))

@bot.command()
async def remove_credits(ctx, member: discord.Member, amount: int):
    try:
        if not is_admin(ctx):
            embed = discord.Embed(title="❌ Permission Denied", description="You don't have permission to use this command.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        user_id = str(member.id)
        if user_id not in users:
            users[user_id] = {"credits": 0, "subdomains": []}

        if users[user_id]["credits"] < amount:
            embed = discord.Embed(title="❌ Insufficient Credits", description=f"{member.mention} does not have enough credits to remove.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        users[user_id]["credits"] -= amount
        save_data(users)

        embed = discord.Embed(
            title="💰 Credits Removed",
            description=f"Removed **{amount} credits** from {member.mention}.\nThey now have **{users[user_id]['credits']} credits**.",
            color=SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Action by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in remove_credits command: {str(e)}")
        await ctx.send(embed=discord.Embed(title="❌ Error", description="An error occurred while removing credits.", color=ERROR_COLOR))

@bot.command()
async def remove_subdomain(ctx, name: str, member: discord.Member = None):
    try:
        if not is_admin(ctx):
            embed = discord.Embed(title="❌ Permission Denied", description="You don't have permission to use this command.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        target_user = member or ctx.author
        user_id = str(target_user.id)

        if user_id not in users or name not in users[user_id].get("subdomains", []):
            embed = discord.Embed(title="❌ Not Found", description=f"Subdomain not found for {target_user.mention}.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        subdomain = f"{name}.{BASE_DOMAIN}"
        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers
        )

        if response.status_code != 200:
            print(f"Cloudflare API error: {response.text}")
            embed = discord.Embed(title="❌ API Error", description=f"Failed to connect to Cloudflare API. Status code: {response.status_code}", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        records = response.json().get("result", [])
        records_to_delete = [r for r in records if r["name"].endswith(f"{name}.{BASE_DOMAIN}")]

        if not records_to_delete:
            embed = discord.Embed(title="⚠️ Warning", description=f"No DNS records found for {subdomain}, but removing from user's list.", color=WARNING_COLOR)
            users[user_id]["subdomains"].remove(name)
            save_data(users)
            return await ctx.send(embed=embed)

        deleted_count = 0
        for record in records_to_delete:
            delete_response = requests.delete(
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record['id']}",
                headers=headers
            )

            if delete_response.status_code == 200 and delete_response.json().get("success"):
                deleted_count += 1

        users[user_id]["subdomains"].remove(name)
        save_data(users)

        embed = discord.Embed(
            title="🗑️ Subdomain Removed",
            description=f"Successfully removed subdomain **{subdomain}** from {target_user.mention}.\nDeleted {deleted_count} DNS records.",
            color=SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Action by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)

        if target_user != ctx.author:
            try:
                user_embed = discord.Embed(
                    title="🗑️ Subdomain Removed",
                    description=f"An administrator has removed your subdomain **{subdomain}**.",
                    color=WARNING_COLOR,
                    timestamp=datetime.now(timezone.utc)
                )
                await target_user.send(embed=user_embed)
            except:
                pass

    except Exception as e:
        print(f"Error in remove_subdomain command: {str(e)}")
        await ctx.send(embed=discord.Embed(title="❌ Error", description=f"Error removing subdomain: {str(e)}", color=ERROR_COLOR))

@bot.command()
async def reset_all(ctx):
    try:
        if not is_admin(ctx):
            embed = discord.Embed(title="❌ Permission Denied", description="You don't have permission to use this command.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        confirmation_string = ''.join(random.choices(string.ascii_letters + string.digits, k=10))
        embed = discord.Embed(
            title="⚠️ Confirmation Required",
            description=f"To confirm resetting all user data, please type the following string:\n\n`{confirmation_string}`",
            color=WARNING_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.content == confirmation_string

        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            embed = discord.Embed(title="❌ Timeout", description="Confirmation string not entered in time.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        global users
        users = {}
        save_data(users)

        embed = discord.Embed(
            title="✅ All User Data Reset",
            description="All user data has been successfully reset.",
            color=SUCCESS_COLOR,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"Action by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in reset_all command: {str(e)}")
        await ctx.send(embed=discord.Embed(title="❌ Error", description="An error occurred while resetting all user data.", color=ERROR_COLOR))

@bot.command()
async def create_subdomain(ctx, name: str):
    try:
        if not is_valid_subdomain(name):
            embed = discord.Embed(title="❌ Invalid Name", description="Invalid subdomain name. Use only alphanumeric characters and hyphens.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        user_id = str(ctx.author.id)
        if user_id not in users:
            users[user_id] = {"credits": 0, "subdomains": []}

        if users[user_id]["credits"] < 10:
            embed = discord.Embed(
                title="❌ Insufficient Credits",
                description="You need 10 credits to create a subdomain. You currently have " + str(users[user_id]["credits"]) + " credits.",
                color=ERROR_COLOR
            )
            return await ctx.send(embed=embed)

        subdomain = f"{name}.{BASE_DOMAIN}"

        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers
        )

        if response.status_code != 200:
            print(f"Cloudflare API error: {response.text}")
            embed = discord.Embed(title="❌ API Error", description=f"Failed to connect to Cloudflare API. Status code: {response.status_code}", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        records = response.json().get("result", [])
        if any(r["name"] == subdomain for r in records):
            embed = discord.Embed(title="⚠️ Already Exists", description=f"Subdomain {subdomain} already exists.", color=WARNING_COLOR)
            return await ctx.send(embed=embed)

        existing_subdomains = users[user_id]["subdomains"]
        if any(subdomain.startswith(f"{existing}.{BASE_DOMAIN}") for existing in existing_subdomains) or name == BASE_DOMAIN:
            embed = discord.Embed(title="❌ Invalid Subdomain", description="You cannot create a subdomain on an existing subdomain or the root domain.", color=ERROR_COLOR)
            return await ctx.send(embed=embed)

        data = {
            "type": "A",
            "name": subdomain,
            "content": "1.2.3.4",
            "ttl": 1,
            "proxied": False
        }

        create_response = requests.post(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers,
            json=data
        )

        if create_response.status_code == 200 or create_response.json().get("success"):
            users[user_id]["credits"] -= 10
            users[user_id]["subdomains"].append(name)
            save_data(users)

            embed = discord.Embed(
                title="✅ Subdomain Created. Remember to delete the example record!",
                description=f"Successfully created subdomain **{subdomain}**\nDefault IP: `1.2.3.4`",
                color=SUCCESS_COLOR,
                timestamp=datetime.now(timezone.utc)
            )
            embed.add_field(name="Next Steps", value="Use `%records` to manage DNS records for this subdomain.")
            embed.set_footer(text=f"Created by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
            await ctx.send(embed=embed)
        else:
            print(f"Failed to create subdomain: {create_response.text}")
            embed = discord.Embed(
                title="❌ Creation Failed",
                description=f"Failed to create subdomain. API Error: {create_response.json().get('errors')}",
                color=ERROR_COLOR
            )
            await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in create_subdomain command: {str(e)}")
        embed = discord.Embed(title="❌ Error", description=f"Error creating subdomain: {str(e)}", color=ERROR_COLOR)
        await ctx.send(embed=embed)

@bot.command()
async def list_subdomains(ctx):
    try:
        user_id = str(ctx.author.id)
        if user_id not in users or not users[user_id].get("subdomains"):
            embed = discord.Embed(
                title="📋 Your Subdomains",
                description="You don't have any subdomains yet.\nUse `%create_subdomain name` to create one.",
                color=INFO_COLOR
            )
            return await ctx.send(embed=embed)

        subdomains = users[user_id]["subdomains"]
        embed = discord.Embed(
            title="📋 Your Subdomains",
            description=f"You have {len(subdomains)} subdomain(s):",
            color=INFO_COLOR,
            timestamp=datetime.now(timezone.utc)
        )

        for subdomain in subdomains:
            full_domain = f"{subdomain}.{BASE_DOMAIN}"
            embed.add_field(name=full_domain, value="Use `%records` to manage DNS records.", inline=False)

        embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Error in list_subdomains command: {str(e)}")
        embed = discord.Embed(title="❌ Error", description="An error occurred while listing your subdomains.", color=ERROR_COLOR)
        await ctx.send(embed=embed)

@bot.command()
async def records(ctx):
    """Interactive DNS record management through DMs"""
    try:
        user_id = str(ctx.author.id)

        initial_embed = discord.Embed(
            title="📬 Check Your DMs",
            description="I've sent you a private message to manage your DNS records.",
            color=INFO_COLOR
        )
        await ctx.send(embed=initial_embed)

        if user_id not in users or not users[user_id].get("subdomains"):
            no_domains_embed = discord.Embed(
                title="❌ No Subdomains",
                description="You don't have any subdomains yet.\nUse `%create_subdomain name` to create one first.",
                color=ERROR_COLOR
            )
            return await ctx.author.send(embed=no_domains_embed)

        active_sessions[user_id] = {
            "step": "select_domain",
            "data": {}
        }

        subdomains = users[user_id]["subdomains"]
        domain_embed = discord.Embed(
            title="🌐 DNS Record Management",
            description="Please select a subdomain to manage by typing its number:",
            color=INFO_COLOR,
            timestamp=datetime.now(timezone.utc)
        )

        for i, subdomain in enumerate(subdomains, 1):
            domain_embed.add_field(name=f"{i}. {subdomain}.{BASE_DOMAIN}", value="Type the number to select", inline=False)

        domain_embed.set_footer(text="Type 'cancel' at any time to exit")
        await ctx.author.send(embed=domain_embed)

    except discord.Forbidden:
        error_embed = discord.Embed(
            title="❌ DM Error",
            description="I couldn't send you a direct message. Please make sure your privacy settings allow DMs from server members.",
            color=ERROR_COLOR
        )
        await ctx.send(embed=error_embed)
    except Exception as e:
        print(f"Error in records command: {str(e)}")
        error_embed = discord.Embed(title="❌ Error", description="An error occurred while setting up record management.", color=ERROR_COLOR)
        await ctx.send(embed=error_embed)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    await bot.process_commands(message)

    if not isinstance(message.channel, discord.DMChannel):
        return

    user_id = str(message.author.id)

    if user_id in active_sessions:
        session = active_sessions[user_id]
        content = message.content.strip().lower()

        if content == "cancel":
            await message.author.send(embed=discord.Embed(
                title="✅ Cancelled",
                description="DNS record management cancelled.",
                color=INFO_COLOR
            ))
            del active_sessions[user_id]
            return

        if session["step"] == "select_domain":
            await process_domain_selection(message, user_id)
        elif session["step"] == "select_action":
            await process_action_selection(message, user_id)
        elif session["step"] == "list_records":
            await process_records_list(message, user_id)
        elif session["step"] == "create_record_type":
            await process_create_record_type(message, user_id)
        elif session["step"] == "create_record_name":
            await process_create_record_name(message, user_id)
        elif session["step"] == "create_record_content":
            await process_create_record_content(message, user_id)
        elif session["step"] == "create_cname_target":
            await process_create_cname_target(message, user_id)
        elif session["step"] == "confirm_create":
            await process_confirm_create(message, user_id)
        elif session["step"] == "select_record_to_delete":
            await process_record_deletion(message, user_id)
        elif session["step"] == "confirm_delete":
            await process_confirm_delete(message, user_id)
        elif session["step"] == "select_record_to_edit":
            await process_record_edit_selection(message, user_id)
        elif session["step"] == "edit_record_content":
            await process_edit_record_content(message, user_id)
        elif session["step"] == "confirm_edit":
            await process_confirm_edit(message, user_id)

async def process_domain_selection(message, user_id):
    try:
        session = active_sessions[user_id]
        subdomains = users[user_id]["subdomains"]

        try:
            selection = int(message.content.strip())
            if selection < 1 or selection > len(subdomains):
                raise ValueError()
        except ValueError:
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid Selection",
                description="Please enter a valid number from the list.",
                color=ERROR_COLOR
            ))
            return

        selected_domain = subdomains[selection - 1]
        session["data"]["domain"] = selected_domain
        session["step"] = "select_action"

        action_embed = discord.Embed(
            title=f"🔧 Managing {selected_domain}.{BASE_DOMAIN}",
            description="What would you like to do?",
            color=INFO_COLOR
        )
        action_embed.add_field(name="1. List Records", value="View all DNS records for this domain", inline=False)
        action_embed.add_field(name="2. Add Record", value="Create a new DNS record", inline=False)
        action_embed.add_field(name="3. Edit Record", value="Modify an existing DNS record", inline=False)
        action_embed.add_field(name="4. Delete Record", value="Remove a DNS record", inline=False)
        action_embed.set_footer(text="Type 'cancel' to exit")

        await message.author.send(embed=action_embed)
    except Exception as e:
        print(f"Error in process_domain_selection: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing your selection.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_action_selection(message, user_id):
    try:
        session = active_sessions[user_id]
        content = message.content.strip()

        if content == "1":
            session["step"] = "list_records"
            await list_domain_records(message.author, user_id)
        elif content == "2":
            session["step"] = "create_record_type"
            type_embed = discord.Embed(
                title="🆕 Create DNS Record",
                description=f"Select the record type for {session['data']['domain']}.{BASE_DOMAIN}:",
                color=INFO_COLOR
            )

            for i, record_type in enumerate(RECORD_TYPES, 1):
                description = ""
                if record_type == "A":
                    description = "Maps a domain to an IPv4 address"
                elif record_type == "AAAA":
                    description = "Maps a domain to an IPv6 address"
                elif record_type == "CNAME":
                    description = "Creates an alias pointing to another domain"
                elif record_type == "TXT":
                    description = "Stores text information (e.g., verification)"
                elif record_type == "MX":
                    description = "Specifies mail servers for the domain"
                elif record_type == "SRV":
                    description = "Specifies location of services"

                type_embed.add_field(name=f"{i}. {record_type}", value=description, inline=False)

            type_embed.set_footer(text="Type 'cancel' to exit")
            await message.author.send(embed=type_embed)
        elif content == "3":
            session["step"] = "select_record_to_edit"
            await list_domain_records_for_edit(message.author, user_id)
        elif content == "4":
            session["step"] = "select_record_to_delete"
            await list_domain_records_for_deletion(message.author, user_id)
        else:
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid Selection",
                description="Please enter a number between 1 and 4.",
                color=ERROR_COLOR
            ))
    except Exception as e:
        print(f"Error in process_action_selection: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing your selection.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def list_domain_records(user, user_id):
    try:
        session = active_sessions[user_id]
        domain = session["data"]["domain"]
        subdomain = f"{domain}.{BASE_DOMAIN}"

        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers
        )

        if response.status_code != 200:
            await user.send(embed=discord.Embed(
                title="❌ API Error",
                description=f"Failed to fetch DNS records. Status code: {response.status_code}",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        records = response.json().get("result", [])
        domain_records = [r for r in records if r["name"].endswith(subdomain)]

        if not domain_records:
            no_records_embed = discord.Embed(
                title="📋 DNS Records",
                description=f"No DNS records found for {subdomain}.",
                color=INFO_COLOR
            )
            no_records_embed.add_field(name="Add Record", value="Type '2' to add a new record", inline=False)
            await user.send(embed=no_records_embed)
        else:
            records_embed = discord.Embed(
                title="📋 DNS Records",
                description=f"Records for {subdomain}:",
                color=INFO_COLOR
            )

            for record in domain_records:
                record_type = record["type"]
                content = record["content"]
                proxied = record["proxied"]
                ttl = "Auto" if record["ttl"] == 1 else record["ttl"]

                value = f"Content: `{content}`\nProxied: `{proxied}`\nTTL: `{ttl}`"
                if record_type == "MX":
                    value += f"\nPriority: `{record.get('priority', 'N/A')}`"

                name = record.get("name").replace(f".{BASE_DOMAIN}", "")
                records_embed.add_field(name=f"{record_type}: {name}", value=value, inline=False)

            records_embed.set_footer(text="Type 'back' to return to action selection or 'cancel' to exit")
            await user.send(embed=records_embed)

        session["step"] = "list_records"
    except Exception as e:
        print(f"Error in list_domain_records: {str(e)}")
        await user.send(embed=discord.Embed(title="❌ Error", description="An error occurred while fetching records.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_records_list(message, user_id):
    content = message.content.strip().lower()
    if content == "back":
        session = active_sessions[user_id]
        session["step"] = "select_action"

        selected_domain = session["data"]["domain"]
        action_embed = discord.Embed(
            title=f"🔧 Managing {selected_domain}.{BASE_DOMAIN}",
            description="What would you like to do?",
            color=INFO_COLOR
        )
        action_embed.add_field(name="1. List Records", value="View all DNS records for this domain", inline=False)
        action_embed.add_field(name="2. Add Record", value="Create a new DNS record", inline=False)
        action_embed.add_field(name="3. Edit Record", value="Modify an existing DNS record", inline=False)
        action_embed.add_field(name="4. Delete Record", value="Remove a DNS record", inline=False)
        action_embed.set_footer(text="Type 'cancel' to exit")

        await message.author.send(embed=action_embed)
    else:
        await message.author.send(embed=discord.Embed(
            title="ℹ️ Navigation",
            description="Type '**back**' to return to the main menu or '**cancel**' to exit.",
            color=INFO_COLOR
        ))

async def process_create_record_type(message, user_id):
    try:
        session = active_sessions[user_id]
        content = message.content.strip()

        try:
            selection = int(content)
            if selection < 1 or selection > len(RECORD_TYPES):
                raise ValueError()
        except ValueError:
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid Selection",
                description="Please enter a valid number from the list.",
                color=ERROR_COLOR
            ))
            return

        record_type = RECORD_TYPES[selection - 1]
        session["data"]["record_type"] = record_type

        if record_type == "CNAME":
            session["step"] = "create_cname_target"
            name_embed = discord.Embed(
                title="🆕 Create DNS Record",
                description="Enter the target domain for the CNAME record (e.g., `google.com`):",
                color=INFO_COLOR
            )
            name_embed.set_footer(text="Type 'cancel' to exit")
            await message.author.send(embed=name_embed)
        else:
            session["step"] = "create_record_name"
            name_embed = discord.Embed(
                title="🆕 Create DNS Record",
                description=f"Enter the name for the {record_type} record (leave blank for the root domain):",
                color=INFO_COLOR
            )
            name_embed.set_footer(text="Type 'cancel' to exit")
            await message.author.send(embed=name_embed)
    except Exception as e:
        print(f"Error in process_create_record_type: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the record type.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_create_record_name(message, user_id):
    try:
        session = active_sessions[user_id]
        record_type = session["data"]["record_type"]
        record_name = message.content.strip()

        if record_type in ["A", "AAAA"] and not is_valid_ip(record_name):
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid IP",
                description="The provided IP address is invalid.",
                color=ERROR_COLOR
            ))
            return

        session["data"]["record_name"] = record_name
        session["step"] = "confirm_create"

        confirm_embed = discord.Embed(
            title="🆕 Create DNS Record",
            description=f"Please confirm the creation of the {record_type} record with the following details:",
            color=INFO_COLOR
        )
        confirm_embed.add_field(name="Type", value=record_type, inline=False)
        confirm_embed.add_field(name="Name", value=record_name, inline=False)
        confirm_embed.set_footer(text="Type 'yes' to confirm or 'no' to cancel")

        await message.author.send(embed=confirm_embed)
    except Exception as e:
        print(f"Error in process_create_record_content: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the record content.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_create_cname_target(message, user_id):
    try:
        session = active_sessions[user_id]
        target_domain = message.content.strip()

        if not is_valid_hostname(target_domain):
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid Hostname",
                description="The provided target domain is invalid.",
                color=ERROR_COLOR
            ))
            return

        session["data"]["cname_target"] = target_domain
        session["step"] = "confirm_create"

        confirm_embed = discord.Embed(
            title="🆕 Create DNS Record",
            description=f"Please confirm the creation of the CNAME record with the following details:",
            color=INFO_COLOR
        )
        confirm_embed.add_field(name="Type", value="CNAME", inline=False)
        confirm_embed.add_field(name="Target Domain", value=target_domain, inline=False)
        confirm_embed.set_footer(text="Type 'yes' to confirm or 'no' to cancel")

        await message.author.send(embed=confirm_embed)
    except Exception as e:
        print(f"Error in process_create_cname_target: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the CNAME target.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_confirm_create(message, user_id):
    try:
        session = active_sessions[user_id]
        content = message.content.strip().lower()

        if content == "yes":
            record_type = session["data"]["record_type"]
            domain = session["data"]["domain"]

            if record_type == "CNAME":
                target_domain = session["data"]["cname_target"]
                subdomain = f"{domain}.{BASE_DOMAIN}"
                data = {
                    "type": record_type,
                    "name": subdomain,
                    "content": target_domain,
                    "ttl": 1,
                    "proxied": False
                }
            else:
                record_name = session["data"]["record_name"]
                subdomain = f"{record_name}.{domain}.{BASE_DOMAIN}" if record_name else f"{domain}.{BASE_DOMAIN}"
                data = {
                    "type": record_type,
                    "name": subdomain,
                    "content": record_name,
                    "ttl": 1,
                    "proxied": False
                }

            create_response = requests.post(
                f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
                headers=headers,
                json=data
            )

            if create_response.status_code == 200 or create_response.json().get("success"):
                await message.author.send(embed=discord.Embed(
                    title="✅ Record Created",
                    description=f"Successfully created the {record_type} record for {subdomain}.",
                    color=SUCCESS_COLOR
                ))
            else:
                print(f"Failed to create record: {create_response.text}")
                await message.author.send(embed=discord.Embed(
                    title="❌ Creation Failed",
                    description=f"Failed to create the record. API Error: {create_response.json().get('errors')}",
                    color=ERROR_COLOR
                ))
        else:
            await message.author.send(embed=discord.Embed(
                title="✅ Cancelled",
                description="Record creation cancelled.",
                color=INFO_COLOR
            ))

        del active_sessions[user_id]
    except Exception as e:
        print(f"Error in process_confirm_create: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while confirming the record creation.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_record_deletion(message, user_id):
    try:
        session = active_sessions[user_id]
        domain = session["data"]["domain"]
        subdomain = f"{domain}.{BASE_DOMAIN}"

        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers
        )

        if response.status_code != 200:
            await message.author.send(embed=discord.Embed(
                title="❌ API Error",
                description=f"Failed to fetch DNS records. Status code: {response.status_code}",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        records = response.json().get("result", [])
        domain_records = [r for r in records if r["name"].endswith(subdomain)]

        if not domain_records:
            await message.author.send(embed=discord.Embed(
                title="❌ No Records",
                description=f"No DNS records found for {subdomain}.",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        delete_embed = discord.Embed(
            title="🗑️ Delete DNS Record",
            description=f"Select a record to delete for {subdomain}:",
            color=INFO_COLOR
        )

        for i, record in enumerate(domain_records, 1):
            record_type = record["type"]
            content = record["content"]
            name = record.get("name").replace(f".{BASE_DOMAIN}", "")
            delete_embed.add_field(name=f"{i}. {record_type}: {name}", value=f"Content: `{content}`", inline=False)

        delete_embed.set_footer(text="Type the number to select or 'cancel' to exit")
        await message.author.send(embed=delete_embed)

        session["step"] = "confirm_delete"
        session["data"]["records"] = domain_records
    except Exception as e:
        print(f"Error in process_record_deletion: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the record deletion.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_confirm_delete(message, user_id):
    try:
        session = active_sessions[user_id]
        content = message.content.strip()

        try:
            selection = int(content)
            if selection < 1 or selection > len(session["data"]["records"]):
                raise ValueError()
        except ValueError:
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid Selection",
                description="Please enter a valid number from the list.",
                color=ERROR_COLOR
            ))
            return

        record = session["data"]["records"][selection - 1]
        record_id = record["id"]

        delete_response = requests.delete(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record_id}",
            headers=headers
        )

        if delete_response.status_code == 200 and delete_response.json().get("success"):
            await message.author.send(embed=discord.Embed(
                title="✅ Record Deleted",
                description=f"Successfully deleted the record for {record['name']}.",
                color=SUCCESS_COLOR
            ))
        else:
            print(f"Failed to delete record: {delete_response.text}")
            await message.author.send(embed=discord.Embed(
                title="❌ Deletion Failed",
                description=f"Failed to delete the record. API Error: {delete_response.json().get('errors')}",
                color=ERROR_COLOR
            ))

        del active_sessions[user_id]
    except Exception as e:
        print(f"Error in process_confirm_delete: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while confirming the record deletion.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_record_edit_selection(message, user_id):
    try:
        session = active_sessions[user_id]
        domain = session["data"]["domain"]
        subdomain = f"{domain}.{BASE_DOMAIN}"

        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers
        )

        if response.status_code != 200:
            await message.author.send(embed=discord.Embed(
                title="❌ API Error",
                description=f"Failed to fetch DNS records. Status code: {response.status_code}",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        records = response.json().get("result", [])
        domain_records = [r for r in records if r["name"].endswith(subdomain)]

        if not domain_records:
            await message.author.send(embed=discord.Embed(
                title="❌ No Records",
                description=f"No DNS records found for {subdomain}.",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        edit_embed = discord.Embed(
            title="✏️ Edit DNS Record",
            description=f"Select a record to edit for {subdomain}:",
            color=INFO_COLOR
        )

        for i, record in enumerate(domain_records, 1):
            record_type = record["type"]
            content = record["content"]
            name = record.get("name").replace(f".{BASE_DOMAIN}", "")
            edit_embed.add_field(name=f"{i}. {record_type}: {name}", value=f"Content: `{content}`", inline=False)

        edit_embed.set_footer(text="Type the number to select or 'cancel' to exit")
        await message.author.send(embed=edit_embed)

        session["step"] = "edit_record_content"
        session["data"]["records"] = domain_records
    except Exception as e:
        print(f"Error in process_record_edit_selection: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the record edit selection.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_edit_record_content(message, user_id):
    try:
        session = active_sessions[user_id]
        content = message.content.strip()

        try:
            selection = int(content)
            if selection < 1 or selection > len(session["data"]["records"]):
                raise ValueError()
        except ValueError:
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid Selection",
                description="Please enter a valid number from the list.",
                color=ERROR_COLOR
            ))
            return

        record = session["data"]["records"][selection - 1]
        session["data"]["record_id"] = record["id"]
        session["step"] = "confirm_edit"

        edit_embed = discord.Embed(
            title="✏️ Edit DNS Record",
            description=f"Enter the new content for the {record['type']} record:",
            color=INFO_COLOR
        )
        edit_embed.set_footer(text="Type 'cancel' to exit")
        await message.author.send(embed=edit_embed)
    except Exception as e:
        print(f"Error in process_edit_record_content: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the record edit content.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def process_confirm_edit(message, user_id):
    try:
        session = active_sessions[user_id]
        new_content = message.content.strip()
        record_id = session["data"]["record_id"]

        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record_id}",
            headers=headers
        )

        if response.status_code != 200:
            await message.author.send(embed=discord.Embed(
                title="❌ API Error",
                description=f"Failed to fetch the DNS record. Status code: {response.status_code}",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        record = response.json().get("result", {})
        record_type = record.get("type")

        if record_type in ["A", "AAAA"] and not is_valid_ip(new_content):
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid IP",
                description="The provided IP address is invalid.",
                color=ERROR_COLOR
            ))
            return

        if record_type == "CNAME" and not is_valid_hostname(new_content):
            await message.author.send(embed=discord.Embed(
                title="❌ Invalid Hostname",
                description="The provided hostname is invalid.",
                color=ERROR_COLOR
            ))
            return

        data = {
            "type": record_type,
            "name": record["name"],
            "content": new_content,
            "ttl": record["ttl"],
            "proxied": record["proxied"]
        }

        update_response = requests.put(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records/{record_id}",
            headers=headers,
            json=data
        )

        if update_response.status_code == 200 and update_response.json().get("success"):
            await message.author.send(embed=discord.Embed(
                title="✅ Record Updated",
                description=f"Successfully updated the {record_type} record for {record['name']}.",
                color=SUCCESS_COLOR
            ))
        else:
            print(f"Failed to update record: {update_response.text}")
            await message.author.send(embed=discord.Embed(
                title="❌ Update Failed",
                description=f"Failed to update the record. API Error: {update_response.json().get('errors')}",
                color=ERROR_COLOR
            ))

        del active_sessions[user_id]
    except Exception as e:
        print(f"Error in process_confirm_edit: {str(e)}")
        await message.author.send(embed=discord.Embed(title="❌ Error", description="An error occurred while confirming the record edit.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def list_domain_records_for_edit(user, user_id):
    try:
        session = active_sessions[user_id]
        domain = session["data"]["domain"]
        subdomain = f"{domain}.{BASE_DOMAIN}"

        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers
        )

        if response.status_code != 200:
            await user.send(embed=discord.Embed(
                title="❌ API Error",
                description=f"Failed to fetch DNS records. Status code: {response.status_code}",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        records = response.json().get("result", [])
        domain_records = [r for r in records if r["name"].endswith(subdomain)]

        if not domain_records:
            await user.send(embed=discord.Embed(
                title="❌ No Records",
                description=f"No DNS records found for {subdomain}.",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        edit_embed = discord.Embed(
            title="✏️ Edit DNS Record",
            description=f"Select a record to edit for {subdomain}:",
            color=INFO_COLOR
        )

        for i, record in enumerate(domain_records, 1):
            record_type = record["type"]
            content = record["content"]
            name = record.get("name").replace(f".{BASE_DOMAIN}", "")
            edit_embed.add_field(name=f"{i}. {record_type}: {name}", value=f"Content: `{content}`", inline=False)

        edit_embed.set_footer(text="Type the number to select or 'cancel' to exit")
        await user.send(embed=edit_embed)

        session["step"] = "edit_record_content"
        session["data"]["records"] = domain_records
    except Exception as e:
        print(f"Error in list_domain_records_for_edit: {str(e)}")
        await user.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the record edit selection.", color=ERROR_COLOR))
        del active_sessions[user_id]

async def list_domain_records_for_deletion(user, user_id):
    try:
        session = active_sessions[user_id]
        domain = session["data"]["domain"]
        subdomain = f"{domain}.{BASE_DOMAIN}"

        response = requests.get(
            f"https://api.cloudflare.com/client/v4/zones/{ZONE_ID}/dns_records",
            headers=headers
        )

        if response.status_code != 200:
            await user.send(embed=discord.Embed(
                title="❌ API Error",
                description=f"Failed to fetch DNS records. Status code: {response.status_code}",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        records = response.json().get("result", [])
        domain_records = [r for r in records if r["name"].endswith(subdomain)]

        if not domain_records:
            await user.send(embed=discord.Embed(
                title="❌ No Records",
                description=f"No DNS records found for {subdomain}.",
                color=ERROR_COLOR
            ))
            del active_sessions[user_id]
            return

        delete_embed = discord.Embed(
            title="🗑️ Delete DNS Record",
            description=f"Select a record to delete for {subdomain}:",
            color=INFO_COLOR
        )

        for i, record in enumerate(domain_records, 1):
            record_type = record["type"]
            content = record["content"]
            name = record.get("name").replace(f".{BASE_DOMAIN}", "")
            delete_embed.add_field(name=f"{i}. {record_type}: {name}", value=f"Content: `{content}`", inline=False)

        delete_embed.set_footer(text="Type the number to select or 'cancel' to exit")
        await user.send(embed=delete_embed)

        session["step"] = "confirm_delete"
        session["data"]["records"] = domain_records
    except Exception as e:
        print(f"Error in list_domain_records_for_deletion: {str(e)}")
        await user.send(embed=discord.Embed(title="❌ Error", description="An error occurred while processing the record deletion selection.", color=ERROR_COLOR))
        del active_sessions[user_id]

# Loop
try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("Invalid token. Please check your Discord bot token.")
except Exception as e:
    print(f"Error starting bot: {str(e)}")
