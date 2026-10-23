import { escapeHtml } from './map.js';

export function getMemberJitter(memberId) {
    let hash = 0;
    for (let i = 0; i < memberId.length; i += 1) {
        hash = ((hash << 5) - hash) + memberId.charCodeAt(i);
        hash |= 0;
    }
    const latOffset = ((hash % 7) - 3) * 0.00004;
    const lngOffset = (((Math.floor(hash / 7)) % 7) - 3) * 0.00004;
    return [latOffset, lngOffset];
}

export function renderConvoyMembersUI({
    members,
    convoyMemberId,
    convoyMembersUl,
    mapView,
}) {
    convoyMembersUl.innerHTML = '';
    const activeMemberIds = new Set();

    members.forEach((member) => {
        const isMe = member.member_id === convoyMemberId;
        const name = member.name || 'Member';
        const label = isMe ? `${name} (You)` : name;

        const item = document.createElement('li');
        if (member.lat == null || member.lng == null) {
            item.textContent = `${label}: waiting for location...`;
        } else {
            const baseLat = Number(member.lat);
            const baseLng = Number(member.lng);
            const [latOffset, lngOffset] = getMemberJitter(member.member_id);
            const markerLatLng = isMe ? [baseLat, baseLng] : [baseLat + latOffset, baseLng + lngOffset];

            item.textContent = `${label}: ${baseLat.toFixed(5)}, ${baseLng.toFixed(5)}`;

            const safeLabel = escapeHtml(label);
            mapView.upsertConvoyMarker(member.member_id, markerLatLng, {
                isMe,
                label: safeLabel,
                popup: { title: label, meta: `${baseLat.toFixed(5)}, ${baseLng.toFixed(5)}` },
            });
            activeMemberIds.add(member.member_id);
        }
        convoyMembersUl.appendChild(item);
    });

    mapView.removeConvoyMarkersExcept(activeMemberIds);
}
