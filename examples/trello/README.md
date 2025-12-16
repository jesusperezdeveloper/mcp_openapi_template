# Trello MCP Example

This directory contains a complete example configuration for creating a Trello MCP server using the template.

## Files

- **service.yaml** - Complete service configuration for Trello
- **helpers.py** - Custom helper tools that provide friendly wrappers around common Trello operations

## Quick Setup

1. Copy the service configuration:
   ```bash
   cp examples/trello/service.yaml config/service.yaml
   ```

2. Download the Trello OpenAPI spec:
   ```bash
   python -m scripts.fetch_openapi \
     --url "https://developer.atlassian.com/cloud/trello/swagger.v3.json" \
     --output openapi/spec.json
   ```

3. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your Auth Gateway credentials
   ```

4. (Optional) Add helper tools - Edit `src/server.py` and add:
   ```python
   from examples.trello.helpers import register_helper_tools

   # After creating the mcp instance
   register_helper_tools(mcp, _auth_params, _client, _require_auth)
   ```

5. Run the server:
   ```bash
   PYTHONPATH=vendor python -m src.server
   ```

## Helper Tools Included

The `helpers.py` file provides these user-friendly tools:

### Reading
- `list_boards()` - List all boards for the authenticated user
- `list_lists(board_id)` - List all lists in a board
- `list_cards(list_id)` - List all cards in a list

### Creating
- `create_card(list_id, name, desc, pos)` - Create a new card
- `create_checklist(card_id, name)` - Create a checklist on a card
- `create_label(board_id, name, color)` - Create a label on a board

### Modifying
- `move_card(card_id, list_id)` - Move a card to another list
- `update_card_name(card_id, new_name)` - Update card name
- `update_card_description(card_id, new_desc)` - Update card description
- `add_label_to_card(card_id, label_id)` - Add a label to a card

### Deleting
- `delete_card(card_id)` - Delete a card
- `delete_checklist(checklist_id)` - Delete a checklist

## Validation

The Trello example includes specific validation for:

- **IDs**: 24 character hexadecimal strings (e.g., `507f1f77bcf86cd799439011`)
- **ShortLinks**: 8 character alphanumeric strings
- **Colors**: `green`, `yellow`, `orange`, `red`, `purple`, `blue`, `sky`, `lime`, `pink`, `black`
- **Positions**: `top`, `bottom`, or positive numbers

## Policies

The configuration blocks destructive operations:

- Deleting boards
- Deleting organizations
- Removing board/organization members

And requires confirmation for:

- Closing boards
- Closing (archiving) lists
