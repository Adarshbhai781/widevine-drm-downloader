import { PrismaClient } from '@prisma/client'
import { execSync } from 'child_process'
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

// Ensure database exists and has schema (for serverless environments)
let dbEnsured = false
export async function ensureDatabase() {
  if (dbEnsured) return
  dbEnsured = true // Set early to prevent concurrent runs

  try {
    // Try a simple query to see if DB is ready
    const testClient = new PrismaClient()
    await testClient.$queryRaw`SELECT 1`
    await testClient.$disconnect()
    return
  } catch {
    // DB not ready, need to create it
  }

  try {
    // Extract file path from DATABASE_URL
    const filePath = dbUrl.replace('file:', '')
    
    // Ensure directory exists
    const dir = path.dirname(filePath)
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }
    
    // Create empty SQLite file if it doesn't exist
    if (!fs.existsSync(filePath)) {
      fs.writeFileSync(filePath, '')
    }
    
    // Run prisma db push to create schema
    execSync('npx prisma db push --accept-data-loss 2>&1', {
      env: { ...process.env, DATABASE_URL: dbUrl },
      timeout: 30000,
      stdio: 'pipe',
    })
  } catch (err) {
    console.error('Database initialization failed:', err)
  }
}

export const db =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === 'development' ? ['query'] : [],
  })

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = db
