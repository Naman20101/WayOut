"""Dijkstra: input adjacency list, output edge path of minimum nonnegative cost."""
import heapq
def shortest_path(adjacency,start,goal,weight):
    queue=[(0.0,start)];cost={start:0.0};parent={}
    while queue:
        total,node=heapq.heappop(queue)
        if total!=cost[node]:continue
        if node==goal:
            path=[]
            while node!=start:
                prev,edge=parent[node];path.append((prev,node,edge));node=prev
            return list(reversed(path)),total
        for nxt,edge in adjacency.get(node,[]):
            w=weight(edge)
            if w is None:continue # blocked / unavailable
            if w<0:raise ValueError('Dijkstra requires nonnegative costs')
            new=total+w
            if new<cost.get(nxt,float('inf')):
                cost[nxt]=new;parent[nxt]=(node,edge);heapq.heappush(queue,(new,nxt))
    raise ValueError('No route is available for these points, mode and simulated closures.')
