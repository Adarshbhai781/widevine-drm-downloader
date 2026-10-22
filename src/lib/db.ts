import { PrismaClient } from '@prisma/client'
import fs from 'fs'
import path from 'path'

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

// For Netlify serverless: use /tmp for SQLite since it's writable
function getDbUrl(): string {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL
  if (process.env.NETLIFY) return 'file:/tmp/adarshdrm.db'
  return 'file:./dev.db'
}

const dbUrl = getDbUrl()
process.env.DATABASE_URL = dbUrl

// SQL to create all tables directly (bypasses prisma db push which fails on serverless)
const CREATE_TABLES_SQL = `
CREATE TABLE IF NOT EXISTS Conversation (
  id TEXT PRIMARY KEY NOT NULL,
  title TEXT NOT NULL DEFAULT 'New Chat',
  model TEXT NOT NULL DEFAULT 'default',
  createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Message (
  id TEXT PRIMARY KEY NOT NULL,
  conversationId TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  toolCalls TEXT,
  toolCallId TEXT,
  metadata TEXT,
  createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (conversationId) REFERENCES Conversation(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ToolLog (
  id TEXT PRIMARY KEY NOT NULL,
  toolName TEXT NOT NULL,
  input TEXT NOT NULL,
  output TEXT,
  duration INTEGER,
  status TEXT NOT NULL DEFAULT 'success',
  createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Settings (
  id TEXT PRIMARY KEY NOT NULL,
  key TEXT NOT NULL UNIQUE,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS VideoJob (
  id TEXT PRIMARY KEY NOT NULL,
  mpdUrl TEXT NOT NULL,
  licenseUrl TEXT NOT NULL DEFAULT 'https://cwip-shaka-proxy.appspot.com/no_auth',
  status TEXT NOT NULL DEFAULT 'pending',
  progress INTEGER NOT NULL DEFAULT 0,
  message TEXT,
  videoPath TEXT,
  videoSize INTEGER,
  duration REAL,
  resolution TEXT,
  keysJson TEXT,
  createdAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
`

// Ensure database exists and has schema (for serverless environments)
let dbEnsured = false
export async function ensureDatabase() {
  if (dbEnsured) return

  try {
    // Try a simple query to see if DB is ready
    const testClient = new PrismaClient()
    await testClient.$queryRaw`SELECT 1 FROM VideoJob LIMIT 1`
    await testClient.$disconnect()
    dbEnsured = true
    return
  } catch {
    // DB not ready, need to create it
  }

  try {
    // Extract file path from DATABASE_URL
    const filePath = dbUrl.replace('file:', '')
    
    // Ensure directory exists
    const dir = path.dirname(filePath)
    if (dir && !fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }
    
    // Create the SQLite file with tables using Prisma's $executeRawUnsafe
    const initClient = new PrismaClient()
    
    // Split SQL and execute each statement
    const statements = CREATE_TABLES_SQL
      .split(';')
      .map(s => s.trim())
      .filter(s => s.length > 0)
    
    for (const stmt of statements) {
      await initClient.$executeRawUnsafe(stmt)
    }
    
    await initClient.$disconnect()
    dbEnsured = true
    console.log('Database initialized successfully at:', filePath)
  } catch (err) {
    console.error('Database initialization failed:', err)
    dbEnsured = true // Mark as ensured anyway to prevent retry loops
  }
}

export const db =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === 'development' ? ['query'] : [],
  })

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = db
