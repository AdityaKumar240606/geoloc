import express from "express";
import path from "path";
import http from "http";
import { Server } from "socket.io";
import pg from "pg";
import ngrok from "@ngrok/ngrok";
import dotenv from "dotenv";
import { fileURLToPath } from "url";

dotenv.config();

// Destructure Pool from pg
const { Pool } = pg;

// Needed if you use __dirname in ES module scope
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();
const server = http.createServer(app);
const io = new Server(server);
const pool = new Pool({
  user: "postgres",  
  host: "localhost",
  database: "tracker_db",    
  password: "aditya", 
  port: 5432,
});

pool.connect((err) => {
  if (err) console.error("Database connection error:", err.stack);
  else console.log("Connected to PostgreSQL (tracker_db)");
});






io.on("connection", (socket)=> {
  console.log("client connected")

  socket.on("location", async (data) => {
    const { latitude, longitude, accuracy, timestamp } = data;

    // Use current time or convert incoming ISO timestamp
    let recordedAt = new Date(timestamp);
    if (isNaN(recordedAt.getTime())) {
      recordedAt = new Date();
    }
    const insertQuery = `
      INSERT INTO location_logs (device_id, latitude, longitude, accuracy, recorded_at)
      VALUES ($1, $2, $3, $4, $5)
      RETURNING id, geom;
    `;

    try {
      await pool.query(insertQuery, [
        socket.id,
        latitude,
        longitude,
        accuracy || null,
        recordedAt
      ]);
      console.log(`Saved point for ${socket.id}`);
    } catch (err) {
      console.error("Error saving location:", err.message);
    }

    // Broadcast to other clients if needed
    socket.broadcast.emit("location", { id: socket.id, ...data });
  });
  });


app.get("/api/route-line", async (req, res) => {
  try {
    const query = `
      SELECT ST_AsGeoJSON(ST_MakeLine(geom ORDER BY recorded_at)) AS route_line
      FROM location_logs
      WHERE recorded_at >= NOW() - INTERVAL '1 hour';
    `;
    const result = await pool.query(query);
    res.json(JSON.parse(result.rows[0].route_line));
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});


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