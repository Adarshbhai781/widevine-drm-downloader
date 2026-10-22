import { PrismaClient } from '@prisma/client'

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined
}

// For Netlify serverless: use /tmp for SQLite since it's writable
// The database will be created automatically on first access
if (!process.env.DATABASE_URL) {
  // Netlify serverless functions have /tmp as writable
  if (process.env.NETLIFY) {
    process.env.DATABASE_URL = 'file:/tmp/adarshdrm.db'
  } else {
    process.env.DATABASE_URL = 'file:./dev.db'
  }
}

export const db =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === 'development' ? ['query'] : [],
  })

if (process.env.NODE_ENV !== 'production') globalForPrisma.prisma = db
