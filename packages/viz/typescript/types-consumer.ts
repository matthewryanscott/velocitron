import {netToDot, type Net} from "./dist/index.js";

const net: Net = {
  name: "move",
  places: [
    {name: "src", accepts: ["job"]},
    {name: "dst", accepts: ["job"]},
  ],
  transitions: [{name: "move", handler: "move"}],
  arcs: [
    {
      from: {place: "src"},
      to: {transition: "move"},
      consume: {type: "job", mode: "consume", weight: 1},
    },
    {
      from: {transition: "move"},
      to: {place: "dst"},
      produce: {type: "job", destination: "dst"},
    },
  ],
};

export function draw(document: Net = net): string {
  return netToDot(document);
}
