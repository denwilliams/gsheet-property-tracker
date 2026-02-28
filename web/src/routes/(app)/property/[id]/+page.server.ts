import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import sql from '$lib/server/db';

export const load: PageServerLoad = async ({ params }) => {
    const [property] = await sql`
        SELECT * FROM properties WHERE id = ${params.id}
    `;

    if (!property) {
        error(404, 'Property not found');
    }

    const changes = await sql`
        SELECT * FROM changes
        WHERE property_id = ${params.id}
        ORDER BY detected_at DESC
        LIMIT 100
    `;

    const snapshots = await sql`
        SELECT * FROM listing_snapshots
        WHERE property_id = ${params.id}
    `;

    return {
        property: {
            ...property,
            last_checked: property.last_checked?.toISOString() ?? null,
        },
        changes: changes.map((c: any) => ({
            ...c,
            detected_at: c.detected_at.toISOString(),
        })),
        snapshots: snapshots.map((s: any) => ({
            ...s,
            fetched_at: s.fetched_at.toISOString(),
            auction_date: s.auction_date?.toISOString() ?? null,
        })),
    };
};
