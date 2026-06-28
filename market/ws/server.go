package ws

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
	"github.com/gorilla/websocket"
	"github.com/tent-of-trials/market/matching"
	"github.com/tent-of-trials/market/types"
	"go.uber.org/zap"
	"go.uber.org/zap"
)

// defaultAllowedOrigins contains safe defaults for local development.
// These are overridden by the ALLOWED_ORIGINS environment variable.
var defaultAllowedOrigins = []string{
	"http://localhost",
	"http://localhost:3000",
	"http://localhost:8080",
	"http://127.0.0.1",
	"http://127.0.0.1:3000",
	"http://127.0.0.1:8080",
}

// getAllowedOrigins returns the list of allowed origins from the ALLOWED_ORIGINS
// environment variable (comma-separated), or the default local development origins.
func getAllowedOrigins() []string {
	if env := os.Getenv("ALLOWED_ORIGINS"); env != "" {
		parts := strings.Split(env, ",")
		origins := make([]string, 0, len(parts))
		for _, o := range parts {
			if trimmed := strings.TrimSpace(o); trimmed != "" {
				origins = append(origins, trimmed)
			}
		}
		return origins
	}
	return defaultAllowedOrigins
}

// isOriginAllowed checks if the given origin is in the allowed list.
// It uses constant-time comparison to mitigate timing attacks.
func isOriginAllowed(origin string, allowed []string) bool {
	for _, a := range allowed {
		if subtle.ConstantTimeCompare([]byte(origin), []byte(a)) == 1 {
			return true
		}
	}
	return false
}

func newUpgrader() websocket.Upgrader {
	return websocket.Upgrader{
		ReadBufferSize:  4096,
		WriteBufferSize: 4096,
		CheckOrigin:     checkOrigin,
	}
}

type Client struct {
	conn     *websocket.Conn
	send     chan []byte
	subs     map[types.Symbol]struct{}
	remote   string
	mu       sync.Mutex
}

type Hub struct {
	clients    map[*Client]struct{}
	register   chan *Client
	unregister chan *Client
	broadcast  chan []byte
	logger     *zap.Logger
	mu         sync.RWMutex
}

type Server struct {
	hub    *Hub
	engine *matching.MatchingEngine
	logger *zap.Logger
	port   int
	srv    *http.Server
}

func NewHub(logger *zap.Logger) *Hub {
	return &Hub{
		clients:    make(map[*Client]struct{}),
		register:   make(chan *Client),
		unregister: make(chan *Client),
		broadcast:  make(chan []byte, 256),
		logger:     logger,
	logger     *zap.Logger
	port       int
	srv        *http.Server
	allowedOrigins []string
}

func NewHub(logger *zap.Logger) *Hub {
		case client := <-h.register:
			h.mu.Lock()
			h.clients[client] = struct{}{}
			h.mu.Unlock()
			h.logger.Info("client connected",
				zap.String("remote", client.remote),
				zap.Int("total", len(h.clients)),
			)

		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				close(client.send)
			}
			h.mu.Unlock()
			h.logger.Info("client disconnected",
				zap.String("remote", client.remote),
				zap.Int("total", len(h.clients)),
			)

		case message := <-h.broadcast:
			h.mu.RLock()
			for client := range h.clients {
	}
}

func NewServer(hub *Hub, engine *matching.MatchingEngine, logger *zap.Logger, port int, allowedOrigins []string) *Server {
	return &Server{
		hub:            hub,
		engine:         engine,
		logger:         logger,
		port:           port,
		allowedOrigins: allowedOrigins,
	}
}

func NewServer(hub *Hub, engine *matching.MatchingEngine, logger *zap.Logger, port int) *Server {
	return &Server{
		hub:    hub,
		engine: engine,
		logger: logger,
		port:   port,
	}
}

func (s *Server) Start() error {
	mux := http.NewServeMux()
	mux.HandleFunc("/ws", s.handleWebSocket)
	mux.HandleFunc("/health", s.handleHealth)
	mux.HandleFunc("/api/v1/trades", s.handleGetTrades)
}

func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	upgrader := newUpgrader()
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		s.logger.Error("websocket upgrade failed", zap.Error(err))
		WriteTimeout: 15 * time.Second,
		IdleTimeout:  60 * time.Second,
	}

	return s.srv.ListenAndServe()
}

func (s *Server) Stop() {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	s.srv.Shutdown(ctx)
}

func (s *Server) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		s.logger.Error("websocket upgrade failed", zap.Error(err))
		return
	}

	client := &Client{
		hub:    s.hub,
		conn:   conn,
		send:   make(chan []byte, 256),
		subs:   make(map[types.Symbol]struct{}),
		remote: r.RemoteAddr,
	}

	s.hub.register <- client

	go client.writePump()
	go client.readPump()
}

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "ok",
		"service": "tent-market",
		"time":    time.Now().Unix(),
	})
}

func (s *Server) handleGetTrades(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
		c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	})
}

// checkOrigin validates the Origin header against the allowed origins list.
// If no Origin header is present, the request is allowed (non-browser clients).
// If the Origin header is present, it must match an allowed origin exactly.
func checkOrigin(r *http.Request) bool {
	origin := r.Header.Get("Origin")
	if origin == "" {
		// Non-browser client or same-origin request; allow
		return true
	}

	allowed := getAllowedOrigins()
	if len(allowed) == 0 {
		// No allowed origins configured; reject for safety
		return false
	}

	return isOriginAllowed(origin, allowed)
}

func (s *Server) handleGetDepth(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]string{"message": "depth endpoint"})
}

func (c *Client) readPump() {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close()
	}()

	c.conn.SetReadLimit(65536)
	c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
		return nil
	})

	for {
		_, message, err := c.conn.ReadMessage()
		if err != nil {
			break
		}

		var event map[string]interface{}
		if err := json.Unmarshal(message, &event); err != nil {
			continue
		}

		c.mu.Lock()

		c.mu.Unlock()
	}
}

func (c *Client) writePump() {
	ticker := time.NewTicker(30 * time.Second)
	defer func() {
		ticker.Stop()
		c.conn.Close()
	}()

	for {
		select {
		case message, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, message); err != nil {
				return
			}

		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(10 * time.Second))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}
