import { NextRequest, NextResponse } from 'next/server';
import { db } from '@/lib/db';

// POST /api/conversations - Create new conversation
export async function POST() {
  try {
    const conversation = await db.conversation.create({
      data: { title: 'New Chat' },
    });
    return NextResponse.json(conversation);
  } catch {
    return NextResponse.json({ error: 'Failed to create conversation' }, { status: 500 });
  }
}

// GET /api/conversations - List all conversations
export async function GET() {
  try {
    const conversations = await db.conversation.findMany({
      orderBy: { updatedAt: 'desc' },
      include: {
        _count: { select: { messages: true } },
      },
    });
    return NextResponse.json(conversations);
  } catch {
    return NextResponse.json({ error: 'Failed to fetch conversations' }, { status: 500 });
  }
}
