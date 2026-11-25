// ブロックの定義・ツールボックス・Python 側に送る簡易 JSON への変換
"use strict";

const DIR6 = [["まえ", "forward"], ["うしろ", "back"], ["ひだり", "left"],
              ["みぎ", "right"], ["うえ", "up"], ["した", "down"]];
const DIR4 = [["まえ", "forward"], ["うしろ", "back"], ["ひだり", "left"], ["みぎ", "right"]];
const TURN2 = [["みぎ", "right"], ["ひだり", "left"]];
const INPUTS = [
  ["みどりボタン", "green"], ["あおボタン", "blue"],
  ["スティックを まえ", "stick_fwd"], ["スティックを うしろ", "stick_back"],
  ["スティックを ひだり", "stick_left"], ["スティックを みぎ", "stick_right"],
];
const INPUT_LABEL = Object.fromEntries(INPUTS.map(([label, v]) => [v, label]));

const COL_EVENT = 50, COL_ACTION = 215, COL_LOOP = 35, COL_DRIVE = 160;

Blockly.common.defineBlocksWithJsonArray([
  { type: "ev_press", message0: "%1 を おしたとき", args0: [{ type: "field_dropdown", name: "INPUT", options: INPUTS }],
    message1: "%1", args1: [{ type: "input_statement", name: "BODY", check: "ACTION" }],
    colour: COL_EVENT, hat: "cap", tooltip: "おした しゅんかんに、なかのブロックを 1かい うごかす" },
  { type: "ev_hold", message0: "%1 を おしているあいだ", args0: [{ type: "field_dropdown", name: "INPUT", options: INPUTS }],
    message1: "%1", args1: [{ type: "input_statement", name: "BODY", check: "DRIVE" }],
    colour: COL_EVENT, hat: "cap", tooltip: "おしているあいだ ずっと うごきつづける" },
  { type: "ev_stick", message0: "スティックで そうじゅうする  さいだいの はやさ %1",
    args0: [{ type: "field_number", name: "SPEED", value: 60, min: 10, max: 100, precision: 1 }],
    colour: COL_EVENT, tooltip: "スティックを たおした ぶんだけ うごく" },

  { type: "a_takeoff", message0: "りりくする", previousStatement: "ACTION", nextStatement: "ACTION", colour: COL_ACTION },
  { type: "a_land", message0: "ちゃくりくする", previousStatement: "ACTION", nextStatement: "ACTION", colour: COL_ACTION },
  { type: "a_move", message0: "%1 に %2 cm すすむ",
    args0: [{ type: "field_dropdown", name: "DIR", options: DIR6 },
            { type: "field_number", name: "CM", value: 50, min: 20, max: 500, precision: 1 }],
    previousStatement: "ACTION", nextStatement: "ACTION", colour: COL_ACTION, tooltip: "20〜500cm" },
  { type: "a_turn", message0: "%1 に %2 ど まわる",
    args0: [{ type: "field_dropdown", name: "DIR", options: TURN2 },
            { type: "field_number", name: "DEG", value: 90, min: 1, max: 360, precision: 1 }],
    previousStatement: "ACTION", nextStatement: "ACTION", colour: COL_ACTION },
  { type: "a_flip", message0: "%1 に ちゅうがえり",
    args0: [{ type: "field_dropdown", name: "DIR", options: DIR4 }],
    previousStatement: "ACTION", nextStatement: "ACTION", colour: COL_ACTION,
    tooltip: "バッテリーが 50%よりすくないと できないよ" },
  { type: "a_wait", message0: "%1 びょう まつ",
    args0: [{ type: "field_number", name: "SEC", value: 1, min: 0.1, max: 10, precision: 0.1 }],
    previousStatement: "ACTION", nextStatement: "ACTION", colour: COL_ACTION },
  { type: "a_repeat", message0: "%1 かい くりかえす", args0: [{ type: "field_number", name: "TIMES", value: 3, min: 1, max: 10, precision: 1 }],
    message1: "%1", args1: [{ type: "input_statement", name: "BODY", check: "ACTION" }],
    previousStatement: "ACTION", nextStatement: "ACTION", colour: COL_LOOP },

  { type: "d_drive", message0: "%1 に うごきつづける はやさ %2",
    args0: [{ type: "field_dropdown", name: "DIR", options: DIR6 },
            { type: "field_number", name: "SPEED", value: 40, min: 10, max: 100, precision: 1 }],
    previousStatement: "DRIVE", nextStatement: "DRIVE", colour: COL_DRIVE },
  { type: "d_spin", message0: "%1 に まわりつづける はやさ %2",
    args0: [{ type: "field_dropdown", name: "DIR", options: TURN2 },
            { type: "field_number", name: "SPEED", value: 50, min: 10, max: 100, precision: 1 }],
    previousStatement: "DRIVE", nextStatement: "DRIVE", colour: COL_DRIVE },
]);

function blk(type, fields) { return { kind: "block", type, fields }; }

const TOOLBOX = {
  kind: "categoryToolbox",
  contents: [
    { kind: "category", name: "イベント", colour: COL_EVENT, contents: [
      { kind: "label", text: "あかボタンは いつでも りりく / ちゃくりく" },
      blk("ev_press", { INPUT: "green" }), blk("ev_hold", { INPUT: "green" }), blk("ev_stick"),
    ] },
    { kind: "category", name: "うごき", colour: COL_ACTION, contents: [
      blk("a_takeoff"), blk("a_land"), blk("a_move"), blk("a_turn"), blk("a_flip"),
    ] },
    { kind: "category", name: "くりかえし", colour: COL_LOOP, contents: [
      blk("a_repeat"), blk("a_wait"),
    ] },
    { kind: "category", name: "うごきつづける", colour: COL_DRIVE, contents: [
      { kind: "label", text: "「おしているあいだ」のなかで つかう" },
      blk("d_drive"), blk("d_spin"),
    ] },
  ],
};

// ---- ワークスペース -> Python に送る JSON ----
function chain(first, convert) {
  const out = [];
  for (let b = first; b; b = b.getNextBlock()) {
    const item = convert(b);
    if (item) out.push(item);
  }
  return out;
}

function actionOf(b) {
  const id = b.id;
  switch (b.type) {
    case "a_takeoff": return { op: "takeoff", id };
    case "a_land": return { op: "land", id };
    case "a_move": return { op: "move", id, dir: b.getFieldValue("DIR"), cm: b.getFieldValue("CM") };
    case "a_turn": return { op: "turn", id, dir: b.getFieldValue("DIR"), deg: b.getFieldValue("DEG") };
    case "a_flip": return { op: "flip", id, dir: b.getFieldValue("DIR") };
    case "a_wait": return { op: "wait", id, sec: b.getFieldValue("SEC") };
    case "a_repeat": return { op: "repeat", id, times: b.getFieldValue("TIMES"),
                              body: chain(b.getInputTargetBlock("BODY"), actionOf) };
    default: return null;
  }
}

function driveOf(b) {
  if (b.type === "d_drive") return { op: "drive", dir: b.getFieldValue("DIR"), speed: b.getFieldValue("SPEED") };
  if (b.type === "d_spin") return { op: "spin", dir: b.getFieldValue("DIR"), speed: b.getFieldValue("SPEED") };
  return null;
}

function workspaceToProgram(ws) {
  const events = [];
  for (const b of ws.getTopBlocks(true)) {
    if (b.type === "ev_press") {
      events.push({ kind: "press", input: b.getFieldValue("INPUT"),
                    script: chain(b.getInputTargetBlock("BODY"), actionOf) });
    } else if (b.type === "ev_hold") {
      events.push({ kind: "hold", input: b.getFieldValue("INPUT"),
                    moves: chain(b.getInputTargetBlock("BODY"), driveOf) });
    } else if (b.type === "ev_stick") {
      events.push({ kind: "stick_drive", speed: b.getFieldValue("SPEED") });
    }
  }
  return { events };
}
