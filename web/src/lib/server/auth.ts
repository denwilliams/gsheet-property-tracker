import { env } from '$env/dynamic/private';
import sql from './db';
import crypto from 'node:crypto';

let _logged = false;

export async function validateCredentials(email: string, password: string): Promise<boolean> {
    if (!_logged) {
        _logged = true;
        console.log(`[auth] AUTH_EMAIL=${env.AUTH_EMAIL ? env.AUTH_EMAIL : '(not set)'}, AUTH_PASSWORD=${env.AUTH_PASSWORD ? '***' : '(not set)'}`);
    }
    return email === env.AUTH_EMAIL && password === env.AUTH_PASSWORD;
}

export async function createSession(email: string): Promise<string> {
    const token = crypto.randomBytes(32).toString('hex');
    const expiresAt = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
    await sql`
        INSERT INTO sessions (token, email, expires_at)
        VALUES (${token}, ${email}, ${expiresAt})
    `;
    return token;
}

export async function getSession(token: string): Promise<string | null> {
    const [session] = await sql`
        SELECT email FROM sessions
        WHERE token = ${token} AND expires_at > NOW()
    `;
    return session?.email ?? null;
}

export async function deleteSession(token: string): Promise<void> {
    await sql`DELETE FROM sessions WHERE token = ${token}`;
}
