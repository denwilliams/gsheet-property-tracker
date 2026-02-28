import { error } from '@sveltejs/kit';
import { readFile } from 'fs/promises';
import { join } from 'path';
import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const IMAGE_DIR = env.IMAGE_DIR || join(process.cwd(), '..', 'data', 'images');

export const GET: RequestHandler = async ({ params }) => {
    const { property_id, filename } = params;

    // Sanitize: property_id is hex, filename is hex.jpg
    if (!/^[a-f0-9]+$/.test(property_id) || !/^[a-f0-9]+\.jpg$/.test(filename)) {
        error(400, 'Invalid parameters');
    }

    const filepath = join(IMAGE_DIR, property_id, filename);

    try {
        const data = await readFile(filepath);
        return new Response(data, {
            headers: {
                'Content-Type': 'image/jpeg',
                'Cache-Control': 'public, max-age=86400',
            },
        });
    } catch {
        error(404, 'Image not found');
    }
};
