// CraftTweaker script for Easy Villagers Iron Farm recipe
// This script removes the default recipe and adds a custom one

// Remove the existing Iron Farm recipe
craftingTable.remove(<item:easy_villagers:iron_farm>);

// Add the new custom Iron Farm recipe
// Pattern:
// Top row:    Glass Pane, Glass Pane, Glass Pane
// Middle row: Glass Pane, Lava Bucket, Glass Pane
// Bottom row: Iron Block, Stone, Iron Block
craftingTable.addShaped("custom_iron_farm", <item:easy_villagers:iron_farm> * 2, [
    [<item:minecraft:glass_pane>, <item:minecraft:glass_pane>, <item:minecraft:glass_pane>],
    [<item:minecraft:glass_pane>, <item:minecraft:lava_bucket>, <item:minecraft:glass_pane>],
    [<item:minecraft:iron_block>, <item:minecraft:stone>, <item:minecraft:iron_block>]
]);

// Remove the existing Stone Waystone recipe
// Try waystones:waystone if waystones:stone_waystone doesn't work
craftingTable.remove(<item:waystones:waystone>);

// Add the new custom Stone Waystone recipe
// Pattern: Pearl in center, surrounded by 4 Stone Bricks
craftingTable.addShaped("custom_stone_waystone", <item:waystones:waystone>, [
    [<item:minecraft:air>, <item:minecraft:stone_bricks>, <item:minecraft:air>],
    [<item:minecraft:stone_bricks>, <item:minecraft:ender_pearl>, <item:minecraft:stone_bricks>],
    [<item:minecraft:air>, <item:minecraft:stone_bricks>, <item:minecraft:air>]
]);

