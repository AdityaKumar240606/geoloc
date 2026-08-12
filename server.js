const express = require("express");
const path = require("path");
const app = express();
const ngrok = require("@ngrok/ngrok");
require("dotenv").config();
const http = require("http");
const { Server } = require("socket.io");

const server = http.createServer(app);
const io = new Server(server);

io.on("connection", (socket)=> {
  console.log("client connected")

  socket.on("location", (data) => {
    console.log("location via socket:", data);

    socket.broadcast.emit("location", {id : socket.id, ...data});});});

async function forwardToApp() {
  const forwarder = await ngrok.forward({
    addr: "localhost:3000",
    authtoken_from_env: true,
    domain: "autograph-glue-spied.ngrok-free.dev",
  });
  console.log(`Available at: ${forwarder.url()}`);
}

forwardToApp();
app.use(express.json());
app.use(express.static(__dirname)); 

server.listen(3000, () => console.log("Server running on http://localhost:3000"));