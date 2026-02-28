import type { PageServerLoad } from './$types';
import sql from '$lib/server/db';

export const load: PageServerLoad = async () => {
    const properties = await sql`
        SELECT p.*,
            EXISTS(
                SELECT 1 FROM changes c
                WHERE c.property_id = p.id
                AND c.detected_at > NOW() - INTERVAL '48 hours'
            ) as has_recent_changes,
            (SELECT MAX(c.detected_at) FROM changes c WHERE c.property_id = p.id)
                as last_change_at
        FROM properties p
        ORDER BY p.updated_at DESC
    `;

    const areas = await sql`
        SELECT DISTINCT area FROM properties WHERE area IS NOT NULL AND area != '' ORDER BY area
    `;

    return {
        properties: properties.map(p => ({
            ...p,
            last_checked: p.last_checked?.toISOString() ?? null,
            last_change_at: p.last_change_at?.toISOString() ?? null,
            created_at: undefined,
            updated_at: undefined,
        })),
        areas: areas.map((a: any) => a.area),
    };
};
