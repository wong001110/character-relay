from echo_masque.api.connector_schemas import DiscordInboundMessage


def test_discord_inbound_message_accepts_attachment_and_embed_metadata() -> None:
    payload = DiscordInboundMessage.model_validate(
        {
            "connection_id": "conn-1",
            "deployment_id": "deployment-1",
            "message_id": "message-1",
            "guild_id": "guild-1",
            "channel_id": "channel-1",
            "author_id": "user-1",
            "author_display_name": "Member",
            "attachments": [
                {
                    "attachment_id": "attachment-1",
                    "url": "https://cdn.discordapp.com/attachments/a/b/cat.png",
                    "proxy_url": "https://media.discordapp.net/attachments/a/b/cat.png",
                    "filename": "cat.png",
                    "content_type": "image/png",
                    "size_bytes": 12345,
                    "width": 640,
                    "height": 480,
                }
            ],
            "embeds": [
                {
                    "embed_type": "video",
                    "url": "https://www.bilibili.com/video/BV1abc/",
                    "title": "Cherry Studio V2 来了，超详细攻略",
                    "description": "真实使用场景分享",
                    "provider_name": "哔哩哔哩",
                    "author_name": "技术爬爬虾",
                }
            ],
        }
    )

    assert payload.attachments[0].attachment_id == "attachment-1"
    assert payload.attachments[0].content_type == "image/png"
    assert payload.attachments[0].size_bytes == 12345
    assert payload.embeds[0].embed_type == "video"
    assert payload.embeds[0].provider_name == "哔哩哔哩"
    assert "Cherry Studio V2" in payload.embeds[0].title
